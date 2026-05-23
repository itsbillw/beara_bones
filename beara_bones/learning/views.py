"""Learning app views: vault browser, auth, uploads, document viewers."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import cast

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, LogoutView
from django import forms
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import (
    CreateDirectoryForm,
    InviteSignupForm,
    LearningLoginForm,
    validate_upload_file,
)
from .markdown_utils import render_markdown
from .models import LearningDirectory, LearningDocument, LearningInvite
from .storage import delete_file, open_file, save_file


def _user_directories(user) -> list[LearningDirectory]:
    return list(LearningDirectory.objects.filter(owner=user).select_related("parent"))


def _directory_tree(user) -> list[LearningDirectory]:
    """Top-level directories for sidebar."""
    return list(
        LearningDirectory.objects.filter(owner=user, parent__isnull=True).order_by(
            "name",
        ),
    )


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
    return list(LearningDocument.objects.filter(owner=user))


def _content_type_from_filename(filename: str) -> LearningDocument.ContentType:
    ext = Path(filename).suffix.lower()
    if ext == ".pdf":
        return cast(LearningDocument.ContentType, LearningDocument.ContentType.PDF)
    return cast(LearningDocument.ContentType, LearningDocument.ContentType.MARKDOWN)


def _title_from_filename(filename: str) -> str:
    return Path(filename).stem.replace("-", " ").replace("_", " ").title()


class LearningLoginView(LoginView):
    template_name = "learning/login.html"
    authentication_form = LearningLoginForm
    redirect_authenticated_user = True

    def get_success_url(self) -> str:
        return str(reverse("learning:vault"))


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


@login_required
@require_http_methods(["GET"])
def vault(request):
    """Vault root: top-level directories."""
    directories = _directory_tree(request.user)
    return render(
        request,
        "learning/vault.html",
        {
            "current_directory": None,
            "directories": directories,
            "child_directories": directories,
            "documents": [],
            "breadcrumbs": [],
            "tree_directories": _user_directories(request.user),
            "mkdir_form": CreateDirectoryForm(),
        },
    )


@login_required
@require_http_methods(["GET"])
def directory_detail(request, dir_id: uuid.UUID):
    """Browse a directory's subfolders and documents."""
    directory = _get_directory_for_user(request.user, dir_id)
    child_directories = list(
        directory.children.filter(owner=request.user).order_by("name"),
    )
    documents = list(directory.documents.filter(owner=request.user).order_by("title"))
    breadcrumbs = directory.get_ancestors() + [directory]
    return render(
        request,
        "learning/vault.html",
        {
            "current_directory": directory,
            "directories": _directory_tree(request.user),
            "child_directories": child_directories,
            "documents": documents,
            "breadcrumbs": breadcrumbs,
            "tree_directories": _user_directories(request.user),
            "mkdir_form": CreateDirectoryForm(),
        },
    )


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


def _save_uploaded_document(user, directory: LearningDirectory, uploaded) -> None:
    doc_id = uuid.uuid4()
    content_type = _content_type_from_filename(uploaded.name)
    storage_key = save_file(
        user.id,
        str(directory.id),
        str(doc_id),
        uploaded.name,
        uploaded,
    )
    LearningDocument.objects.create(
        id=doc_id,
        owner=user,
        directory=directory,
        title=_title_from_filename(uploaded.name),
        original_filename=Path(uploaded.name).name,
        content_type=content_type,
        storage_key=storage_key,
        size_bytes=uploaded.size,
    )


@login_required
@require_http_methods(["POST"])
def upload(request):
    """Upload one or more PDF or markdown files into a directory."""
    directory_id = request.POST.get("directory_id")
    if not directory_id:
        messages.error(request, "Select a folder before uploading.")
        return redirect("learning:vault")

    directory = _get_directory_for_user(request.user, uuid.UUID(directory_id))
    files = request.FILES.getlist("file")
    if not files:
        messages.error(request, "No files selected.")
        return redirect("learning:directory", dir_id=directory.id)

    uploaded_names: list[str] = []
    for uploaded in files:
        try:
            validate_upload_file(uploaded)
        except forms.ValidationError as exc:
            messages.error(request, f"{uploaded.name}: {exc.messages[0]}")
            continue

        _save_uploaded_document(request.user, directory, uploaded)
        uploaded_names.append(uploaded.name)

    if len(uploaded_names) == 1:
        messages.success(request, f'Uploaded "{uploaded_names[0]}".')
    elif uploaded_names:
        messages.success(request, f"Uploaded {len(uploaded_names)} files.")

    return redirect("learning:directory", dir_id=directory.id)


@login_required
@require_http_methods(["GET"])
def document_view(request, doc_id: uuid.UUID):
    """Render PDF or markdown document."""
    document = _get_document_for_user(request.user, doc_id)
    breadcrumbs = document.directory.get_ancestors() + [document.directory]

    if document.content_type == LearningDocument.ContentType.PDF:
        return render(
            request,
            "learning/document_pdf.html",
            {
                "document": document,
                "current_directory": document.directory,
                "breadcrumbs": breadcrumbs,
                "tree_directories": _user_directories(request.user),
                "raw_url": reverse(
                    "learning:document_raw",
                    kwargs={"doc_id": document.id},
                ),
            },
        )

    try:
        raw = open_file(document.storage_key).decode("utf-8")
    except (FileNotFoundError, UnicodeDecodeError):
        raise Http404("Document content not found") from None

    html_content = render_markdown(raw, _all_user_documents(request.user))
    return render(
        request,
        "learning/document_markdown.html",
        {
            "document": document,
            "current_directory": document.directory,
            "html_content": html_content,
            "breadcrumbs": breadcrumbs,
            "tree_directories": _user_directories(request.user),
        },
    )


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
@require_http_methods(["POST"])
def document_delete(request, doc_id: uuid.UUID):
    """Delete a document and its storage."""
    document = _get_document_for_user(request.user, doc_id)
    directory_id = document.directory_id
    delete_file(document.storage_key)
    document.delete()
    messages.success(request, "Document deleted.")
    return redirect("learning:directory", dir_id=directory_id)
