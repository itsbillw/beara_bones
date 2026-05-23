"""Learning vault models: invites, directories, documents, activity, tags."""

from __future__ import annotations

import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone
from django.utils.text import slugify

User = get_user_model()


def _default_invite_expiry() -> timezone.datetime:
    days = getattr(settings, "LEARNING_INVITE_EXPIRY_DAYS", 7)
    return timezone.now() + timedelta(days=days)


def generate_invite_token() -> str:
    return secrets.token_urlsafe(32)


class LearningInvite(models.Model):
    """Invite-only signup token created by staff."""

    email = models.EmailField()
    token = models.CharField(max_length=64, unique=True, default=generate_invite_token)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="learning_invites_created",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(default=_default_invite_expiry)
    used_at = models.DateTimeField(null=True, blank=True)
    used_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="learning_invite_used",
    )

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"Invite for {self.email}"

    @property
    def is_valid(self) -> bool:
        if self.used_at is not None:
            return False
        return bool(timezone.now() < self.expires_at)


class LearningDirectory(models.Model):
    """User-owned folder; supports nesting via parent FK."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="learning_directories",
    )
    name = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "parent", "name"],
                name="learning_unique_directory_name_per_parent",
            ),
        ]

    def __str__(self) -> str:
        return str(self.name)

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            base = slugify(self.name) or "folder"
            self.slug = base
        super().save(*args, **kwargs)

    def get_ancestors(self) -> list[LearningDirectory]:
        """Return list of ancestors from root to parent (excluding self)."""
        ancestors: list[LearningDirectory] = []
        current = self.parent
        while current is not None:
            ancestors.insert(0, current)
            current = current.parent
        return ancestors


class LearningTag(models.Model):
    """User-scoped tag for organising documents."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="learning_tags",
    )
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=100)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["owner", "slug"],
                name="learning_unique_tag_slug_per_owner",
            ),
        ]

    def __str__(self) -> str:
        return str(self.name)

    def save(self, *args, **kwargs) -> None:
        if not self.slug:
            self.slug = slugify(self.name) or "tag"
        super().save(*args, **kwargs)


class LearningDocument(models.Model):
    """User-owned file stored in MinIO (or local media fallback)."""

    class ContentType(models.TextChoices):
        PDF = "pdf", "PDF"
        MARKDOWN = "markdown", "Markdown"

    class Language(models.TextChoices):
        SPANISH = "es", "Spanish"
        ENGLISH = "en", "English"
        BLANK = "", "—"

    class Difficulty(models.TextChoices):
        BEGINNER = "beginner", "Beginner"
        INTERMEDIATE = "intermediate", "Intermediate"
        ADVANCED = "advanced", "Advanced"
        BLANK = "", "—"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="learning_documents",
    )
    directory = models.ForeignKey(
        LearningDirectory,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    title = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255)
    content_type = models.CharField(max_length=16, choices=ContentType.choices)
    storage_key = models.CharField(max_length=512)
    size_bytes = models.PositiveIntegerField(default=0)
    language = models.CharField(
        max_length=8,
        choices=Language.choices,
        blank=True,
        default="",
    )
    topic = models.CharField(max_length=255, blank=True, default="")
    author = models.CharField(max_length=255, blank=True, default="")
    difficulty = models.CharField(
        max_length=16,
        choices=Difficulty.choices,
        blank=True,
        default="",
    )
    thumbnail_key = models.CharField(max_length=512, blank=True, default="")
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        default="",
        db_index=True,
    )
    tags = models.ManyToManyField(LearningTag, blank=True, related_name="documents")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["title"]

    def __str__(self) -> str:
        return str(self.title)


class LearningActivity(models.Model):
    """Tracks document views and PDF reading progress per user."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="learning_activities",
    )
    document = models.ForeignKey(
        LearningDocument,
        on_delete=models.CASCADE,
        related_name="activities",
    )
    last_page = models.PositiveIntegerField(null=True, blank=True)
    last_viewed_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-last_viewed_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "document"],
                name="learning_unique_activity_per_user_doc",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} → {self.document_id}"


class LearningStarred(models.Model):
    """User-starred documents for quick access."""

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="learning_starred",
    )
    document = models.ForeignKey(
        LearningDocument,
        on_delete=models.CASCADE,
        related_name="starred_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "document"],
                name="learning_unique_starred_per_user_doc",
            ),
        ]

    def __str__(self) -> str:
        return f"★ {self.document_id} ({self.user_id})"
