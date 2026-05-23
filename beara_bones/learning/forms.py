"""Forms for learning vault: invites, uploads, directory creation."""

from __future__ import annotations

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils.text import slugify

from .models import LearningDirectory, LearningDocument, LearningTag

User = get_user_model()

ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown"}

NOTE_TEMPLATES: dict[str, str] = {
    "blank": "",
    "book-note": """---
type: book-note
lang: en
tags: []
status: reading
---

# Book title

## Summary


## Key ideas

""",
    "concept": """---
type: concept
lang: en
tags: []
---

# Concept name

## Definition


## Related

""",
    "spanish": """---
type: spanish
lang: es
tags: []
---

# Título

## Notas


## Vocabulario

""",
}


class LearningLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Username"},
        ),
    )
    password = forms.CharField(
        widget=forms.PasswordInput(
            attrs={"class": "form-control", "placeholder": "Password"},
        ),
    )
    remember_me = forms.BooleanField(
        required=False,
        initial=False,
        label="Remember me",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )


class InviteSignupForm(UserCreationForm):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"class": "form-control", "readonly": True}),
    )

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        for field in ("username", "password1", "password2"):
            self.fields[field].widget.attrs.update({"class": "form-control"})


class CreateDirectoryForm(forms.ModelForm):
    class Meta:
        model = LearningDirectory
        fields = ("name",)
        widgets = {
            "name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Folder name"},
            ),
        }


class DocumentMetadataForm(forms.ModelForm):
    tag_names = forms.CharField(
        required=False,
        help_text="Comma-separated tag names",
        widget=forms.TextInput(
            attrs={"class": "form-control", "placeholder": "verbs, django"},
        ),
    )

    class Meta:
        model = LearningDocument
        fields = ("title", "language", "topic", "author", "difficulty")
        widgets = {
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "language": forms.Select(attrs={"class": "form-select"}),
            "topic": forms.TextInput(attrs={"class": "form-control"}),
            "author": forms.TextInput(attrs={"class": "form-control"}),
            "difficulty": forms.Select(attrs={"class": "form-select"}),
        }

    def save_tags(self, owner) -> None:
        assert self.instance.pk is not None
        raw = self.cleaned_data.get("tag_names", "")
        names = [n.strip() for n in raw.split(",") if n.strip()]
        tags: list[LearningTag] = []
        for name in names:
            tag, _ = LearningTag.objects.get_or_create(
                owner=owner,
                slug=slugify(name) or "tag",
                defaults={"name": name},
            )
            tags.append(tag)
        self.instance.tags.set(tags)


class RenameDirectoryForm(forms.Form):
    name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )


class RenameDocumentForm(forms.Form):
    title = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )


class MoveItemForm(forms.Form):
    directory_id = forms.UUIDField()


class CreateNoteForm(forms.Form):
    template = forms.ChoiceField(
        choices=[(k, k.replace("-", " ").title()) for k in NOTE_TEMPLATES],
    )
    title = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )


def validate_upload_file(uploaded) -> None:
    """Raise ValidationError if the uploaded file is not allowed."""
    name = uploaded.name
    if ".." in name or name.startswith("/"):
        raise forms.ValidationError("Invalid filename.")
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise forms.ValidationError("Only PDF and Markdown files are allowed.")
    max_bytes = getattr(settings, "LEARNING_MAX_UPLOAD_MB", 25) * 1024 * 1024
    if uploaded.size > max_bytes:
        raise forms.ValidationError(
            f"File too large. Maximum size is {getattr(settings, 'LEARNING_MAX_UPLOAD_MB', 25)} MB.",
        )


class UploadDocumentForm(forms.Form):
    file = forms.FileField(
        widget=forms.FileInput(
            attrs={"class": "form-control", "accept": ".pdf,.md,.markdown"},
        ),
    )

    def clean_file(self):
        uploaded = self.cleaned_data["file"]
        validate_upload_file(uploaded)
        return uploaded
