"""Document search helpers (MariaDB FULLTEXT in prod, icontains in dev)."""

from __future__ import annotations

from django.db import connection
from django.db.models import Q, QuerySet

from .models import LearningDocument


def search_documents(user, query: str, limit: int = 50) -> QuerySet[LearningDocument]:
    """Search owned documents by title and filename."""
    query = query.strip()
    if not query:
        return LearningDocument.objects.none()

    base = LearningDocument.objects.filter(owner=user).select_related("directory")

    if connection.vendor == "mysql":
        return base.extra(
            where=[
                "MATCH(title, original_filename) AGAINST (%s IN BOOLEAN MODE)",
            ],
            params=[query],
        ).order_by("title")[:limit]

    return base.filter(
        Q(title__icontains=query) | Q(original_filename__icontains=query),
    ).order_by("title")[:limit]
