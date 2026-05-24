"""Learning app views: vault browser, auth, uploads, document viewers."""

from __future__ import annotations

import hashlib
import io
import json
import uuid
from pathlib import Path
from typing import Any, cast

from django import forms
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.text import slugify
from django.views.decorators.http import require_http_methods

from .forms import (
    NOTE_TEMPLATES,
    CreateDirectoryForm,
    CreateNoteForm,
    DocumentMetadataForm,
    InviteSignupForm,
    LearningLoginForm,
    MoveItemForm,
    RenameDirectoryForm,
    RenameDocumentForm,
    validate_upload_file,
)
from .markdown_utils import (
    build_preview_index,
    cached_render_markdown,
    get_user_markdown_raw_contents,
    parse_frontmatter,
)
from .markdown_utils import (
    find_backlinks_with_contents as find_backlinks,
)
from .models import (
    LearningActivity,
    LearningDirectory,
    LearningDocument,
    LearningInvite,
    LearningStarred,
    LearningTag,
)
from .storage import (
    delete_file,
    open_file,
    overwrite_file,
    save_file,
    save_thumbnail,
)
from .thumbnail_utils import generate_pdf_thumbnail
from .tree_utils import active_directory_path, build_directory_tree
from .zip_utils import ZipImportError, build_directory_zip, extract_zip_to_directory


def _get_directory_for_user(user, dir_id: uuid.UUID) -> LearningDirectory:
    return cast(
        LearningDirectory,
        get_object_or_404(LearningDirectory, id=dir_id, owner=user),
    )


def _get_document_for_user(user, doc_id: uuid.UUID) -> LearningDocument:
    return cast(
        LearningDocument,
        get_object_or_404(LearningDocument, id=doc_id, owner=user),
    )


def _all_user_documents(user) -> list[LearningDocument]:
    return list(
        LearningDocument.objects.filter(owner=user).prefetch_related("tags"),
    )


def _user_directories(user) -> list[LearningDirectory]:
    return list(LearningDirectory.objects.filter(owner=user).select_related("parent"))


def _content_type_from_filename(filename: str) -> LearningDocument.ContentType:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return cast(LearningDocument.ContentType, LearningDocument.ContentType.PDF)
    return cast(LearningDocument.ContentType, LearningDocument.ContentType.MARKDOWN)


def _title_from_filename(filename: str) -> str:
    return Path(filename).stem.replace("-", " ").replace("_", " ").title()


def _compute_content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _record_activity(
    user,
    document: LearningDocument,
    last_page: int | None = None,
) -> None:
    defaults: dict[str, Any] = {"last_viewed_at": timezone.now()}
    if last_page is not None:
        defaults["last_page"] = last_page
    LearningActivity.objects.update_or_create(
        user=user,
        document=document,
        defaults=defaults,
    )


def _starred_ids(user) -> set[uuid.UUID]:
    return set(
        LearningStarred.objects.filter(user=user).values_list("document_id", flat=True),
    )


def _build_sibling_map(
    all_dirs: list[LearningDirectory],
) -> dict[int | None, list[LearningDirectory]]:
    from collections import defaultdict

    by_parent: dict[int | None, list[LearningDirectory]] = defaultdict(list)
    for directory in all_dirs:
        by_parent[directory.parent_id].append(directory)
    for siblings in by_parent.values():
        siblings.sort(key=lambda d: d.name.lower())
    return by_parent


def _breadcrumb_siblings(
    breadcrumbs: list[LearningDirectory],
    sibling_map: dict[int | None, list[LearningDirectory]],
) -> list[dict[str, Any]]:
    """Sibling folders at each breadcrumb level for dropdown navigation."""
    levels: list[dict[str, Any]] = []
    for crumb in breadcrumbs:
        siblings = sibling_map.get(crumb.parent_id, [])
        levels.append({"current": crumb, "siblings": siblings})
    return levels


def _is_directory_descendant(
    candidate_id: uuid.UUID,
    ancestor_id: uuid.UUID,
    parent_map: dict[uuid.UUID, uuid.UUID | None],
) -> bool:
    current: uuid.UUID | None = candidate_id
    while current is not None:
        if current == ancestor_id:
            return True
        current = parent_map.get(current)
    return False


def _apply_filters(
    documents: list[LearningDocument],
    content_filter: str | None,
    tag_slug: str | None,
) -> list[LearningDocument]:
    result = documents
    if content_filter == "pdf":
        result = [d for d in result if d.content_type == LearningDocument.ContentType.PDF]
    elif content_filter == "markdown":
        result = [d for d in result if d.content_type == LearningDocument.ContentType.MARKDOWN]
    if tag_slug:
        result = [d for d in result if any(t.slug == tag_slug for t in d.tags.all())]
    return result


def _sort_items(
    directories: list[LearningDirectory],
    documents: list[LearningDocument],
    sort_by: str,
) -> tuple[list[LearningDirectory], list[LearningDocument]]:
    if sort_by == "date":
        directories = sorted(directories, key=lambda d: d.updated_at, reverse=True)
        documents = sorted(documents, key=lambda d: d.updated_at, reverse=True)
    elif sort_by == "size":
        documents = sorted(documents, key=lambda d: d.size_bytes, reverse=True)
    elif sort_by == "type":
        documents = sorted(documents, key=lambda d: d.content_type)
    else:
        directories = sorted(directories, key=lambda d: d.name.lower())
        documents = sorted(documents, key=lambda d: d.title.lower())
    return directories, documents


def _vault_context(
    request,
    current_directory: LearningDirectory | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """Shared context for vault and document pages."""
    user = request.user
    all_dirs = _user_directories(user)
    tree_nodes = build_directory_tree(all_dirs)
    active_path = active_directory_path(current_directory)
    sibling_map = _build_sibling_map(all_dirs)
    all_tags = list(LearningTag.objects.filter(owner=user).order_by("name"))
    starred = _starred_ids(user)

    content_filter = request.GET.get("type") or ""
    tag_slug = request.GET.get("tag") or ""
    sort_by = request.GET.get("sort") or "name"

    ctx: dict[str, Any] = {
        "current_directory": current_directory,
        "tree_nodes": tree_nodes,
        "active_path": active_path,
        "sibling_map": sibling_map,
        "all_tags": all_tags,
        "starred_ids": starred,
        "content_filter": content_filter,
        "tag_slug": tag_slug,
        "sort_by": sort_by,
        "mkdir_form": CreateDirectoryForm(),
        "search_query": request.GET.get("q", ""),
    }
    ctx.update(extra)
    return ctx


def _vault_context_with_breadcrumbs(
    request,
    breadcrumbs: list[LearningDirectory],
    **extra: Any,
) -> dict[str, Any]:
    ctx = _vault_context(request, **extra)
    ctx["breadcrumbs"] = breadcrumbs
    ctx["breadcrumb_levels"] = _breadcrumb_siblings(breadcrumbs, ctx["sibling_map"])
    return ctx


def _maybe_generate_thumbnail(document: LearningDocument, data: bytes) -> None:
    if document.content_type != LearningDocument.ContentType.PDF:
        return
    png = generate_pdf_thumbnail(data)
    if png:
        thumb_key = save_thumbnail(str(document.id), png)
        document.thumbnail_key = thumb_key
        document.save(update_fields=["thumbnail_key"])


def _save_uploaded_document(
    user,
    directory: LearningDirectory,
    uploaded,
    *,
    warn_duplicates: bool = True,
) -> tuple[LearningDocument, str | None]:
    data = uploaded.read()
    uploaded.seek(0)
    content_hash = _compute_content_hash(data)

    duplicate_msg: str | None = None
    if warn_duplicates:
        duplicate = (
            LearningDocument.objects.filter(
                owner=user,
                content_hash=content_hash,
            )
            .exclude(content_hash="")
            .first()
        )
        if duplicate:
            duplicate_msg = f'"{uploaded.name}" looks like a duplicate of "{duplicate.title}".'

    doc_id = uuid.uuid4()
    content_type = _content_type_from_filename(uploaded.name)
    storage_key = save_file(
        user.id,
        str(directory.id),
        str(doc_id),
        uploaded.name,
        io.BytesIO(data),
    )
    document = LearningDocument.objects.create(
        id=doc_id,
        owner=user,
        directory=directory,
        title=_title_from_filename(uploaded.name),
        original_filename=Path(uploaded.name).name,
        content_type=content_type,
        storage_key=storage_key,
        size_bytes=len(data),
        content_hash=content_hash,
    )
    _maybe_generate_thumbnail(document, data)
    return document, duplicate_msg


class LearningLoginView(LoginView):
    template_name = "learning/login.html"
    authentication_form = LearningLoginForm
    redirect_authenticated_user = True

    def get_success_url(self) -> str:
        return str(reverse("learning:vault"))

    def form_valid(self, form):
        remember = form.cleaned_data.get("remember_me")
        if remember:
            self.request.session.set_expiry(1209600)  # 2 weeks
        else:
            self.request.session.set_expiry(0)
        return super().form_valid(form)


class LearningLogoutView(LogoutView):
    next_page = reverse_lazy("learning:vault")


@require_http_methods(["GET", "POST"])
def join(request, token: str):
    """Accept invite and create account."""
    invite = get_object_or_404(LearningInvite, token=token)
    if not invite.is_valid:
        return render(
            request,
            "learning/join_invalid.html",
            {"invite": invite},
            status=400,
        )

    if request.method == "POST":
        form = InviteSignupForm(request.POST)
        if form.is_valid():
            user = form.save(commit=False)
            user.email = invite.email
            user.save()
            invite.used_at = timezone.now()
            invite.used_by = user
            invite.save(update_fields=["used_at", "used_by"])
            login(request, user)
            messages.success(request, "Welcome! Your learning vault is ready.")
            return redirect("learning:vault")
    else:
        form = InviteSignupForm(initial={"email": invite.email})

    return render(request, "learning/join.html", {"form": form, "invite": invite})


def _recent_documents(user, limit: int = 15) -> list[LearningDocument]:
    activities = (
        LearningActivity.objects.filter(user=user)
        .select_related("document", "document__directory")
        .order_by("-last_viewed_at")[:limit]
    )
    return [a.document for a in activities]


def _starred_documents(user) -> list[LearningDocument]:
    starred = (
        LearningStarred.objects.filter(user=user)
        .select_related("document", "document__directory")
        .order_by("-created_at")
    )
    return [s.document for s in starred]


@login_required
@require_http_methods(["GET"])
def vault(request):
    """Vault root: top-level directories, recent, and starred."""
    directories = list(
        LearningDirectory.objects.filter(
            owner=request.user,
            parent__isnull=True,
        ).order_by("name"),
    )
    child_directories, documents = _sort_items(
        directories,
        [],
        request.GET.get("sort") or "name",
    )
    ctx = _vault_context(
        request,
        current_directory=None,
        child_directories=child_directories,
        documents=documents,
        breadcrumbs=[],
        recent_documents=_recent_documents(request.user),
        starred_documents=_starred_documents(request.user),
        breadcrumb_levels=[],
    )
    return render(request, "learning/vault.html", ctx)


@login_required
@require_http_methods(["GET"])
def directory_detail(request, dir_id: uuid.UUID):
    """Browse a directory's subfolders and documents."""
    directory = _get_directory_for_user(request.user, dir_id)
    child_directories = list(
        directory.children.filter(owner=request.user).order_by("name"),
    )
    documents = list(
        directory.documents.filter(owner=request.user).prefetch_related("tags"),
    )
    content_filter = request.GET.get("type")
    tag_slug = request.GET.get("tag")
    sort_by = request.GET.get("sort") or "name"
    documents = _apply_filters(documents, content_filter, tag_slug)
    child_directories, documents = _sort_items(child_directories, documents, sort_by)
    breadcrumbs = directory.get_ancestors() + [directory]
    ctx = _vault_context_with_breadcrumbs(
        request,
        breadcrumbs,
        current_directory=directory,
        child_directories=child_directories,
        documents=documents,
        recent_documents=[],
        starred_documents=[],
    )
    return render(request, "learning/vault.html", ctx)


@login_required
@require_http_methods(["GET"])
def search(request):
    """Search documents by title and filename."""
    query = (request.GET.get("q") or "").strip()
    results: list[LearningDocument] = []
    if query:
        results = list(
            LearningDocument.objects.filter(owner=request.user)
            .filter(
                Q(title__icontains=query) | Q(original_filename__icontains=query),
            )
            .select_related("directory")
            .order_by("title")[:50],
        )
    ctx = _vault_context(
        request,
        query=query,
        results=results,
    )
    return render(request, "learning/search.html", ctx)


@login_required
@require_http_methods(["POST"])
def mkdir(request):
    """Create a new directory under current parent (or root)."""
    parent_id = request.POST.get("parent_id") or None
    parent = None
    if parent_id:
        parent = _get_directory_for_user(request.user, uuid.UUID(parent_id))

    form = CreateDirectoryForm(request.POST)
    if form.is_valid():
        directory = form.save(commit=False)
        directory.owner = request.user
        directory.parent = parent
        directory.save()
        messages.success(request, f'Created folder "{directory.name}".')
        if parent:
            return redirect("learning:directory", dir_id=parent.id)
        return redirect("learning:vault")
    messages.error(request, "Could not create folder. Check the name and try again.")
    if parent:
        return redirect("learning:directory", dir_id=parent.id)
    return redirect("learning:vault")


@login_required
@require_http_methods(["POST"])
def upload(request):
    """Upload one or more PDF or markdown files into a directory."""
    directory_id = request.POST.get("directory_id")
    if not directory_id:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse(
                {"error": "Select a folder before uploading."},
                status=400,
            )
        messages.error(request, "Select a folder before uploading.")
        return redirect("learning:vault")

    directory = _get_directory_for_user(request.user, uuid.UUID(directory_id))
    files = request.FILES.getlist("file")
    if not files:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"error": "No files selected."}, status=400)
        messages.error(request, "No files selected.")
        return redirect("learning:directory", dir_id=directory.id)

    uploaded_names: list[str] = []
    for uploaded in files:
        try:
            validate_upload_file(uploaded)
        except forms.ValidationError as exc:
            msg = f"{uploaded.name}: {exc.messages[0]}"
            if request.headers.get("X-Requested-With") == "XMLHttpRequest":
                return JsonResponse({"error": msg}, status=400)
            messages.error(request, msg)
            continue

        _, dup_msg = _save_uploaded_document(request.user, directory, uploaded)
        if dup_msg:
            messages.warning(request, dup_msg)
        uploaded_names.append(uploaded.name)

    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"uploaded": uploaded_names, "count": len(uploaded_names)})

    if len(uploaded_names) == 1:
        messages.success(request, f'Uploaded "{uploaded_names[0]}".')
    elif uploaded_names:
        messages.success(request, f"Uploaded {len(uploaded_names)} files.")

    return redirect("learning:directory", dir_id=directory.id)


@login_required
@require_http_methods(["POST"])
def create_note(request):
    """Create a new markdown note from a template."""
    directory_id = request.POST.get("directory_id")
    if not directory_id:
        messages.error(request, "Select a folder first.")
        return redirect("learning:vault")

    directory = _get_directory_for_user(request.user, uuid.UUID(directory_id))
    form = CreateNoteForm(request.POST)
    if not form.is_valid():
        messages.error(request, "Could not create note.")
        return redirect("learning:directory", dir_id=directory.id)

    template_key = form.cleaned_data["template"]
    title = form.cleaned_data["title"]
    body = NOTE_TEMPLATES.get(template_key, "")
    if template_key == "blank" and not body:
        body = f"# {title}\n\n"
    elif "# " not in body[:200]:
        body = f"# {title}\n\n{body}"

    filename = slugify(title) or "note"
    filename = f"{filename}.md"
    content = body.encode("utf-8")
    buffer: io.BytesIO = io.BytesIO(content)
    buffer.name = filename
    buffer.size = len(content)

    doc, _ = _save_uploaded_document(
        request.user,
        directory,
        buffer,
        warn_duplicates=False,
    )
    if doc:
        doc.title = title
        doc.save(update_fields=["title"])
        messages.success(request, f'Created note "{title}".')
        return redirect("learning:document_edit", doc_id=doc.id)
    return redirect("learning:directory", dir_id=directory.id)


@login_required
@require_http_methods(["GET"])
def document_view(request, doc_id: uuid.UUID):
    """Render PDF or markdown document."""
    document = _get_document_for_user(request.user, doc_id)
    breadcrumbs = document.directory.get_ancestors() + [document.directory]
    _record_activity(request.user, document)

    if document.content_type == LearningDocument.ContentType.PDF:
        activity = LearningActivity.objects.filter(
            user=request.user,
            document=document,
        ).first()
        split_note = None
        note_id = request.GET.get("note")
        if note_id:
            split_note = _get_document_for_user(request.user, uuid.UUID(note_id))
        folder_notes = list(
            LearningDocument.objects.filter(
                owner=request.user,
                directory=document.directory,
                content_type=LearningDocument.ContentType.MARKDOWN,
            ).order_by("title"),
        )
        ctx = _vault_context_with_breadcrumbs(
            request,
            breadcrumbs,
            document=document,
            current_directory=document.directory,
            raw_url=reverse("learning:document_raw", kwargs={"doc_id": document.id}),
            initial_page=activity.last_page if activity and activity.last_page else 1,
            progress_url=reverse(
                "learning:document_progress",
                kwargs={"doc_id": document.id},
            ),
            split_note=split_note,
            folder_notes=folder_notes,
            is_starred=LearningStarred.objects.filter(
                user=request.user,
                document=document,
            ).exists(),
        )
        return render(request, "learning/document_pdf.html", ctx)

    try:
        raw = open_file(document.storage_key).decode("utf-8")
    except (FileNotFoundError, UnicodeDecodeError):
        raise Http404("Document content not found") from None

    all_docs = _all_user_documents(request.user)
    raw_contents = get_user_markdown_raw_contents(request.user.id, all_docs)
    raw_contents[str(document.id)] = raw

    frontmatter, body = parse_frontmatter(raw)
    previews = build_preview_index(all_docs, raw_contents)
    html_content = cached_render_markdown(document, body, all_docs, previews)
    backlinks = find_backlinks(document, all_docs, raw_contents)

    starred = _starred_ids(request.user)
    ctx = _vault_context_with_breadcrumbs(
        request,
        breadcrumbs,
        document=document,
        current_directory=document.directory,
        html_content=html_content,
        frontmatter=frontmatter,
        backlinks=backlinks,
        is_starred=document.id in starred,
    )
    return render(request, "learning/document_markdown.html", ctx)


@login_required
@require_http_methods(["GET", "POST"])
def document_edit(request, doc_id: uuid.UUID):
    """Edit markdown document content."""
    document = _get_document_for_user(request.user, doc_id)
    if document.content_type != LearningDocument.ContentType.MARKDOWN:
        raise Http404("Only markdown documents can be edited")

    breadcrumbs = document.directory.get_ancestors() + [document.directory]

    if request.method == "POST":
        content = request.POST.get("content", "")
        data = content.encode("utf-8")
        size = overwrite_file(document.storage_key, io.BytesIO(data))
        document.size_bytes = size
        document.content_hash = _compute_content_hash(data)
        document.save(update_fields=["size_bytes", "content_hash", "updated_at"])
        messages.success(request, "Note saved.")
        return redirect("learning:document", doc_id=document.id)

    try:
        raw = open_file(document.storage_key).decode("utf-8")
    except (FileNotFoundError, UnicodeDecodeError):
        raise Http404("Document content not found") from None

    all_docs = _all_user_documents(request.user)
    note_titles = sorted(
        {d.title for d in all_docs if d.content_type == LearningDocument.ContentType.MARKDOWN},
    )

    ctx = _vault_context_with_breadcrumbs(
        request,
        breadcrumbs,
        document=document,
        current_directory=document.directory,
        content=raw,
        note_titles_json=json.dumps(note_titles),
    )
    return render(request, "learning/document_edit.html", ctx)


@login_required
@require_http_methods(["GET"])
def document_raw(request, doc_id: uuid.UUID):
    """Stream raw file bytes for PDF.js or download."""
    document = _get_document_for_user(request.user, doc_id)
    try:
        data = open_file(document.storage_key)
    except FileNotFoundError:
        raise Http404("Document not found") from None

    if document.content_type == LearningDocument.ContentType.PDF:
        content_type = "application/pdf"
    else:
        content_type = "text/markdown; charset=utf-8"

    response = HttpResponse(data, content_type=content_type)
    response["Content-Disposition"] = f'inline; filename="{document.original_filename}"'
    return response


@login_required
@require_http_methods(["GET"])
def document_thumbnail(request, doc_id: uuid.UUID):
    """Serve document thumbnail PNG."""
    document = _get_document_for_user(request.user, doc_id)
    if not document.thumbnail_key:
        if document.content_type == LearningDocument.ContentType.PDF:
            try:
                data = open_file(document.storage_key)
                _maybe_generate_thumbnail(document, data)
            except FileNotFoundError:
                raise Http404("Thumbnail not found") from None
        if not document.thumbnail_key:
            raise Http404("Thumbnail not found")

    try:
        data = open_file(document.thumbnail_key)
    except FileNotFoundError:
        raise Http404("Thumbnail not found") from None

    return HttpResponse(data, content_type="image/png")


@login_required
@require_http_methods(["POST"])
def document_progress(request, doc_id: uuid.UUID):
    """Save PDF reading progress."""
    document = _get_document_for_user(request.user, doc_id)
    try:
        payload = json.loads(request.body)
        page = int(payload.get("page", 1))
    except (json.JSONDecodeError, TypeError, ValueError):
        return JsonResponse({"error": "Invalid page"}, status=400)

    _record_activity(request.user, document, last_page=max(1, page))
    return JsonResponse({"ok": True, "page": page})


@login_required
@require_http_methods(["POST"])
def document_meta(request, doc_id: uuid.UUID):
    """Update document metadata and tags."""
    document = _get_document_for_user(request.user, doc_id)
    form = DocumentMetadataForm(request.POST, instance=document)
    if form.is_valid():
        form.save()
        form.save_tags(request.user)
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"ok": True})
        messages.success(request, "Metadata updated.")
    else:
        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return JsonResponse({"error": form.errors}, status=400)
        messages.error(request, "Could not update metadata.")
    return redirect("learning:document", doc_id=document.id)


@login_required
@require_http_methods(["POST"])
def document_star(request, doc_id: uuid.UUID):
    """Toggle starred status."""
    document = _get_document_for_user(request.user, doc_id)
    starred = LearningStarred.objects.filter(user=request.user, document=document)
    if starred.exists():
        starred.delete()
        is_starred = False
    else:
        LearningStarred.objects.create(user=request.user, document=document)
        is_starred = True
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return JsonResponse({"starred": is_starred})
    return redirect(request.META.get("HTTP_REFERER", reverse("learning:vault")))


@login_required
@require_http_methods(["POST"])
def document_delete(request, doc_id: uuid.UUID):
    """Delete a document and its storage."""
    document = _get_document_for_user(request.user, doc_id)
    directory_id = document.directory_id
    if document.thumbnail_key:
        delete_file(document.thumbnail_key)
    delete_file(document.storage_key)
    document.delete()
    messages.success(request, "Document deleted.")
    return redirect("learning:directory", dir_id=directory_id)


@login_required
@require_http_methods(["POST"])
def directory_rename(request, dir_id: uuid.UUID):
    """Rename a directory."""
    directory = _get_directory_for_user(request.user, dir_id)
    form = RenameDirectoryForm(request.POST)
    if form.is_valid():
        directory.name = form.cleaned_data["name"]
        directory.slug = slugify(directory.name) or "folder"
        directory.save(update_fields=["name", "slug", "updated_at"])
        messages.success(request, "Folder renamed.")
    else:
        messages.error(request, "Could not rename folder.")
    return redirect("learning:directory", dir_id=directory.id)


@login_required
@require_http_methods(["POST"])
def directory_move(request, dir_id: uuid.UUID):
    """Move a directory to a new parent."""
    directory = _get_directory_for_user(request.user, dir_id)
    form = MoveItemForm(request.POST)
    if form.is_valid():
        target_id = form.cleaned_data["directory_id"]
        if target_id == directory.id:
            messages.error(request, "Cannot move folder into itself.")
        else:
            new_parent = _get_directory_for_user(request.user, target_id)
            parent_map = {d.id: d.parent_id for d in _user_directories(request.user)}
            if _is_directory_descendant(new_parent.id, directory.id, parent_map):
                messages.error(request, "Cannot move folder into its own subfolder.")
            else:
                directory.parent = new_parent
                directory.save(update_fields=["parent", "updated_at"])
                messages.success(request, "Folder moved.")
                return redirect("learning:directory", dir_id=new_parent.id)
    else:
        messages.error(request, "Could not move folder.")
    return redirect("learning:directory", dir_id=directory.id)


@login_required
@require_http_methods(["POST"])
def document_rename(request, doc_id: uuid.UUID):
    """Rename a document title."""
    document = _get_document_for_user(request.user, doc_id)
    form = RenameDocumentForm(request.POST)
    if form.is_valid():
        document.title = form.cleaned_data["title"]
        document.save(update_fields=["title", "updated_at"])
        messages.success(request, "Document renamed.")
    else:
        messages.error(request, "Could not rename document.")
    return redirect("learning:directory", dir_id=document.directory_id)


@login_required
@require_http_methods(["POST"])
def document_move(request, doc_id: uuid.UUID):
    """Move a document to another directory."""
    document = _get_document_for_user(request.user, doc_id)
    form = MoveItemForm(request.POST)
    if form.is_valid():
        target = _get_directory_for_user(
            request.user,
            form.cleaned_data["directory_id"],
        )
        document.directory = target
        document.save(update_fields=["directory", "updated_at"])
        messages.success(request, "Document moved.")
        return redirect("learning:directory", dir_id=target.id)
    messages.error(request, "Could not move document.")
    return redirect("learning:directory", dir_id=document.directory_id)


@login_required
@require_http_methods(["POST"])
def directory_import_zip(request, dir_id: uuid.UUID):
    """Import a zip archive into a directory."""
    directory = _get_directory_for_user(request.user, dir_id)
    zip_upload = request.FILES.get("file")
    if not zip_upload:
        messages.error(request, "No zip file provided.")
        return redirect("learning:directory", dir_id=directory.id)

    try:
        dirs, docs = extract_zip_to_directory(
            request.user,
            directory,
            zip_upload,
            lambda user, dir_obj, buf: _save_uploaded_document(user, dir_obj, buf)[0],
        )
        messages.success(request, f"Imported {docs} file(s) and {dirs} folder(s).")
    except ZipImportError as exc:
        messages.error(request, str(exc))
    except Exception:
        messages.error(request, "Could not import zip file.")
    return redirect("learning:directory", dir_id=directory.id)


@login_required
@require_http_methods(["GET"])
def directory_export_zip(request, dir_id: uuid.UUID):
    """Export a directory as a zip download."""
    directory = _get_directory_for_user(request.user, dir_id)
    buffer = build_directory_zip(directory)
    response = HttpResponse(buffer.getvalue(), content_type="application/zip")
    response["Content-Disposition"] = f'attachment; filename="{directory.name}.zip"'
    return response


@login_required
@require_http_methods(["GET"])
def note_titles_api(request):
    """JSON list of markdown note titles for wikilink autocomplete."""
    titles = list(
        LearningDocument.objects.filter(
            owner=request.user,
            content_type=LearningDocument.ContentType.MARKDOWN,
        ).values_list("title", flat=True),
    )
    return JsonResponse({"titles": sorted(titles)})
