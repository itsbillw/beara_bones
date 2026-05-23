"""Django admin for learning vault."""

from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html

from .models import LearningDirectory, LearningDocument, LearningInvite


@admin.register(LearningInvite)
class LearningInviteAdmin(admin.ModelAdmin):
    list_display = (
        "email",
        "created_at",
        "expires_at",
        "used_at",
        "is_valid",
        "signup_link",
    )
    list_filter = ("used_at",)
    readonly_fields = ("token", "created_at", "used_at", "used_by", "signup_link")
    fields = (
        "email",
        "token",
        "created_by",
        "created_at",
        "expires_at",
        "used_at",
        "used_by",
        "signup_link",
    )

    def save_model(self, request, obj, form, change) -> None:
        if not change and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)

    @admin.display(boolean=True, description="Valid")
    def is_valid(self, obj: LearningInvite) -> bool:
        return obj.is_valid

    @admin.display(description="Signup URL")
    def signup_link(self, obj: LearningInvite) -> str:
        if not obj.token:
            return "—"
        url = reverse("learning:join", kwargs={"token": obj.token})
        return str(format_html('<a href="{url}">{url}</a>', url=url))


@admin.register(LearningDirectory)
class LearningDirectoryAdmin(admin.ModelAdmin):
    list_display = ("name", "owner", "parent", "created_at")
    list_filter = ("owner",)
    search_fields = ("name", "owner__username")


@admin.register(LearningDocument)
class LearningDocumentAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "owner",
        "directory",
        "content_type",
        "size_bytes",
        "created_at",
    )
    list_filter = ("owner", "content_type")
    search_fields = ("title", "original_filename", "owner__username")
