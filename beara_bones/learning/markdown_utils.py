"""Markdown rendering with wikilink resolution for vault-style notes."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import bleach  # type: ignore[import-untyped]
import markdown as md_lib  # type: ignore[import-untyped]

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
    "a": ["href", "title", "class"],
    "span": ["class"],
    "code": ["class"],
    "pre": ["class"],
    "th": ["align"],
    "td": ["align"],
}


def _build_link_index(documents: list[LearningDocument]) -> dict[str, str]:
    """Map lowercase title/filename stems to document view URLs."""
    from django.urls import reverse

    index: dict[str, str] = {}
    for doc in documents:
        url = reverse("learning:document", kwargs={"doc_id": doc.id})
        index[doc.title.lower()] = url
        stem = doc.original_filename.rsplit(".", 1)[0].lower()
        index[stem.lower()] = url
    return index


def resolve_wikilinks(text: str, link_index: dict[str, str]) -> str:
    """Replace [[wikilinks]] with HTML links or missing-note spans."""

    def replacer(match: re.Match[str]) -> str:
        target = match.group(1).strip()
        alias = (match.group(2) or target).strip()
        url = link_index.get(target.lower())
        if url:
            return f'<a href="{url}" class="wikilink">{alias}</a>'
        return f'<span class="wikilink-missing" title="Note not found">{alias}</span>'

    return WIKILINK_PATTERN.sub(replacer, text)


def render_markdown(content: str, documents: list[LearningDocument]) -> str:
    """Render markdown to sanitized HTML with wikilink resolution."""
    link_index = _build_link_index(documents)
    with_wikilinks = resolve_wikilinks(content, link_index)
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
