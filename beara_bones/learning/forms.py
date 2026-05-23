"""Forms for learning vault: invites, uploads, directory creation."""

from __future__ import annotations

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm

from .models import LearningDirectory

User = get_user_model()

ALLOWED_EXTENSIONS = {".pdf", ".md", ".markdown"}


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
