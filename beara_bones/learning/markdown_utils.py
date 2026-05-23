"""Markdown rendering, wikilinks, backlinks, frontmatter, and caching."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import bleach  # type: ignore[import-untyped]
import frontmatter
import markdown as md_lib  # type: ignore[import-untyped]
from django.core.cache import cache

if TYPE_CHECKING:
    from learning.models import LearningDocument

WIKILINK_PATTERN = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")

ALLOWED_TAGS = [
    "a",
    "blockquote",
    "br",
    "code",
    "del",
    "em",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "hr",
    "li",
    "ol",
    "p",
    "pre",
    "strong",
    "table",
    "tbody",
    "td",
    "th",
    "thead",
    "tr",
    "ul",
    "span",
]
ALLOWED_ATTRIBUTES = {
    "a": ["href", "title", "class", "data-bs-toggle", "data-bs-content"],
    "span": ["class"],
    "code": ["class"],
    "pre": ["class"],
    "th": ["align"],
    "td": ["align"],
}


def split_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Return (metadata dict, body markdown)."""
    post = frontmatter.loads(content)
    meta = dict(post.metadata) if post.metadata else {}
    return meta, post.content


def strip_frontmatter(content: str) -> str:
    _, body = split_frontmatter(content)
    return body


def _build_link_index(documents: list[LearningDocument]) -> dict[str, str]:
    from django.urls import reverse

    index: dict[str, str] = {}
    for doc in documents:
        url = reverse("learning:document", kwargs={"doc_id": doc.id})
        index[doc.title.lower()] = url
        stem = doc.original_filename.rsplit(".", 1)[0].lower()
        index[stem.lower()] = url
    return index


def _preview_snippet(text: str, limit: int = 200) -> str:
    plain = re.sub(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]", r"\1", text)
    plain = re.sub(r"[#*_>`\-]", "", plain)
    plain = " ".join(plain.split())
    if len(plain) <= limit:
        return plain
    return plain[: limit - 1].rstrip() + "…"


def resolve_wikilinks(
    text: str,
    link_index: dict[str, str],
    previews: dict[str, str] | None = None,
) -> str:
    previews = previews or {}

    def replacer(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        alias = (match.group(2) or target).strip()
        url = link_index.get(target.lower())
        if url:
            preview = previews.get(target.lower(), "")
            title_attr = f' title="{preview}"' if preview else ""
            popover = (
                f' data-bs-toggle="popover" data-bs-trigger="hover" '
                f'data-bs-content="{preview}"'
                if preview
                else ""
            )
            return f'<a href="{url}" class="wikilink"{title_attr}{popover}>{alias}</a>'
        return f'<span class="wikilink-missing" title="Note not found">{alias}</span>'

    return WIKILINK_PATTERN.sub(replacer, text)


def find_backlinks(
    target: LearningDocument,
    documents: list[LearningDocument],
) -> list[LearningDocument]:
    """Documents that wikilink to the target note."""
    from .storage import open_file

    target_names = {
        target.title.lower(),
        target.original_filename.rsplit(".", 1)[0].lower(),
    }
    backlinks: list[LearningDocument] = []
    for doc in documents:
        if doc.id == target.id or doc.content_type != doc.ContentType.MARKDOWN:
            continue
        try:
            raw = open_file(doc.storage_key).decode("utf-8")
        except (FileNotFoundError, UnicodeDecodeError):
            continue
        body = strip_frontmatter(raw)
        for match in WIKILINK_PATTERN.finditer(body):
            if match.group(1).strip().lower() in target_names:
                backlinks.append(doc)
                break
    return backlinks


def build_previews(documents: list[LearningDocument]) -> dict[str, str]:
    from .storage import open_file

    previews: dict[str, str] = {}
    for doc in documents:
        if doc.content_type != doc.ContentType.MARKDOWN:
            continue
        try:
            raw = open_file(doc.storage_key).decode("utf-8")
            body = strip_frontmatter(raw)
            snippet = _preview_snippet(body)
            previews[doc.title.lower()] = snippet
            previews[doc.original_filename.rsplit(".", 1)[0].lower()] = snippet
        except (FileNotFoundError, UnicodeDecodeError):
            continue
    return previews


def render_markdown(content: str, documents: list[LearningDocument]) -> str:
    """Render markdown to sanitized HTML with wikilinks and hover previews."""
    _, body = split_frontmatter(content)
    link_index = _build_link_index(documents)
    previews = build_previews(documents)
    with_wikilinks = resolve_wikilinks(body, link_index, previews)
    html = md_lib.markdown(
        with_wikilinks,
        extensions=["fenced_code", "tables", "nl2br"],
        output_format="html5",
    )
    return str(
        bleach.clean(
            html,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            strip=True,
        ),
    )


def render_markdown_cached(
    document: LearningDocument,
    documents: list[LearningDocument],
    raw: str,
) -> str:
    cache_key = f"learning:md:{document.id}:{document.updated_at.timestamp()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return str(cached)
    html = render_markdown(raw, documents)
    cache.set(cache_key, html, timeout=3600)
    return html


def parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Alias used by views."""
    return split_frontmatter(content)


def build_preview_index(
    documents: list[LearningDocument],
    raw_contents: dict[str, str],
) -> dict[str, str]:
    """Build wikilink preview snippets from preloaded raw content."""
    previews: dict[str, str] = {}
    for doc in documents:
        if doc.content_type != doc.ContentType.MARKDOWN:
            continue
        raw = raw_contents.get(str(doc.id))
        if raw is None:
            continue
        body = strip_frontmatter(raw)
        snippet = _preview_snippet(body)
        previews[doc.title.lower()] = snippet
        previews[doc.original_filename.rsplit(".", 1)[0].lower()] = snippet
    return previews


def cached_render_markdown(
    document: LearningDocument,
    body: str,
    documents: list[LearningDocument],
    previews: dict[str, str],
) -> str:
    cache_key = f"learning:md:{document.id}:{document.updated_at.timestamp()}"
    cached = cache.get(cache_key)
    if cached is not None:
        return str(cached)
    link_index = _build_link_index(documents)
    with_wikilinks = resolve_wikilinks(body, link_index, previews)
    html = md_lib.markdown(
        with_wikilinks,
        extensions=["fenced_code", "tables", "nl2br"],
        output_format="html5",
    )
    result = str(
        bleach.clean(
            html,
            tags=ALLOWED_TAGS,
            attributes=ALLOWED_ATTRIBUTES,
            strip=True,
        ),
    )
    cache.set(cache_key, result, timeout=3600)
    return result


def find_backlinks_with_contents(
    target: LearningDocument,
    documents: list[LearningDocument],
    raw_contents: dict[str, str],
) -> list[LearningDocument]:
    """Documents that wikilink to target, using preloaded content."""
    target_names = {
        target.title.lower(),
        target.original_filename.rsplit(".", 1)[0].lower(),
    }
    backlinks: list[LearningDocument] = []
    for doc in documents:
        if doc.id == target.id or doc.content_type != doc.ContentType.MARKDOWN:
            continue
        raw = raw_contents.get(str(doc.id))
        if raw is None:
            continue
        body = strip_frontmatter(raw)
        for match in WIKILINK_PATTERN.finditer(body):
            if match.group(1).strip().lower() in target_names:
                backlinks.append(doc)
                break
    return backlinks
