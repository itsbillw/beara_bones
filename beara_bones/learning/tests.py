"""Tests for the learning vault app."""

from __future__ import annotations

import io
import tempfile
import uuid
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from learning.models import LearningDirectory, LearningDocument, LearningInvite

User = get_user_model()


class LearningAuthTests(TestCase):
    def test_vault_redirects_when_anonymous(self) -> None:
        response = self.client.get(reverse("learning:vault"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/learning/login/", response.url)

    def test_login_page_accessible(self) -> None:
        response = self.client.get(reverse("learning:login"))
        self.assertEqual(response.status_code, 200)


class LearningInviteTests(TestCase):
    def setUp(self) -> None:
        self.staff = User.objects.create_superuser("staff", "staff@example.com", "pass")
        self.invite = LearningInvite.objects.create(
            email="learner@example.com",
            created_by=self.staff,
        )

    def test_valid_invite_signup(self) -> None:
        url = reverse("learning:join", kwargs={"token": self.invite.token})
        response = self.client.post(
            url,
            {
                "username": "learner",
                "email": "learner@example.com",
                "password1": "complex-pass-123",  # pragma: allowlist secret
                "password2": "complex-pass-123",  # pragma: allowlist secret
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("learning:vault"))
        self.assertTrue(User.objects.filter(username="learner").exists())
        self.invite.refresh_from_db()
        self.assertIsNotNone(self.invite.used_at)

    def test_used_invite_rejected(self) -> None:
        self.invite.used_at = timezone.now()
        self.invite.save()
        response = self.client.get(
            reverse("learning:join", kwargs={"token": self.invite.token}),
        )
        self.assertEqual(response.status_code, 400)

    def test_expired_invite_rejected(self) -> None:
        self.invite.expires_at = timezone.now() - timedelta(days=1)
        self.invite.save()
        response = self.client.get(
            reverse("learning:join", kwargs={"token": self.invite.token}),
        )
        self.assertEqual(response.status_code, 400)


class LearningIsolationTests(TestCase):
    def setUp(self) -> None:
        self.user_a = User.objects.create_user("alice", "a@example.com", "pass")
        self.user_b = User.objects.create_user("bob", "b@example.com", "pass")
        self.dir_a = LearningDirectory.objects.create(
            owner=self.user_a,
            name="Notes",
            slug="notes",
        )
        self.doc_a = LearningDocument.objects.create(
            owner=self.user_a,
            directory=self.dir_a,
            title="Alice Note",
            original_filename="alice.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="users/1/x/y_alice.md",
            size_bytes=10,
        )

    @patch("learning.views.open_file", return_value=b"# Hello")
    def test_user_b_cannot_view_user_a_document(self, _mock_open: object) -> None:
        self.client.force_login(self.user_b)
        response = self.client.get(
            reverse("learning:document", kwargs={"doc_id": self.doc_a.id}),
        )
        self.assertEqual(response.status_code, 404)

    @patch("learning.views.open_file", return_value=b"%PDF-1.4")
    def test_user_b_cannot_access_raw_file(self, _mock_open: object) -> None:
        self.doc_a.content_type = LearningDocument.ContentType.PDF
        self.doc_a.save()
        self.client.force_login(self.user_b)
        response = self.client.get(
            reverse("learning:document_raw", kwargs={"doc_id": self.doc_a.id}),
        )
        self.assertEqual(response.status_code, 404)


class LearningVaultTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("vaultuser", "v@example.com", "pass")
        self.client.force_login(self.user)

    def test_vault_renders_view_toggle(self) -> None:
        response = self.client.get(reverse("learning:vault"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "learning-view-toggle")
        self.assertContains(response, 'data-view="grid"')
        self.assertContains(response, 'data-view="list"')

    def test_mkdir_creates_directory(self) -> None:
        response = self.client.post(reverse("learning:mkdir"), {"name": "Courses"})
        self.assertEqual(response.status_code, 302)
        self.assertTrue(
            LearningDirectory.objects.filter(owner=self.user, name="Courses").exists(),
        )

    @patch("learning.views.save_file", return_value="users/1/dir/doc_test.md")
    def test_upload_markdown(self, _mock_save: object) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        content = b"# My note\n\nHello world."
        upload = SimpleUploadedFile("my-note.md", content, content_type="text/markdown")
        response = self.client.post(
            reverse("learning:upload"),
            {"directory_id": str(directory.id), "file": upload},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LearningDocument.objects.filter(owner=self.user).count(), 1)

    @patch("learning.views.save_file", return_value="users/1/dir/doc_test.md")
    def test_upload_multiple_files(self, mock_save: MagicMock) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        files = [
            SimpleUploadedFile("note-one.md", b"# One", content_type="text/markdown"),
            SimpleUploadedFile("note-two.md", b"# Two", content_type="text/markdown"),
        ]
        response = self.client.post(
            reverse("learning:upload"),
            {"directory_id": str(directory.id), "file": files},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LearningDocument.objects.filter(owner=self.user).count(), 2)
        self.assertEqual(mock_save.call_count, 2)

    @patch("learning.views.open_file")
    def test_markdown_viewer_renders(self, mock_open: MagicMock) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        doc = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Note",
            original_filename="note.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="key",
            size_bytes=20,
        )
        mock_open.return_value = b"# Title\n\nSome content."
        response = self.client.get(
            reverse("learning:document", kwargs={"doc_id": doc.id}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Title")

    @patch("learning.views.open_file")
    def test_wikilink_resolves(self, mock_open: MagicMock) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        target = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Target Note",
            original_filename="target.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="target-key",
            size_bytes=10,
        )
        source = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Source",
            original_filename="source.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="source-key",
            size_bytes=10,
        )
        mock_open.return_value = b"See [[Target Note]] for details."
        response = self.client.get(
            reverse("learning:document", kwargs={"doc_id": source.id}),
        )
        self.assertEqual(response.status_code, 200)
        expected_url = reverse("learning:document", kwargs={"doc_id": target.id})
        self.assertContains(response, expected_url)

    @patch("learning.views.open_file", return_value=b"%PDF-1.4 fake")
    def test_pdf_viewer_page(self, _mock_open: object) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Papers",
            slug="papers",
        )
        doc = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Paper",
            original_filename="paper.pdf",
            content_type=LearningDocument.ContentType.PDF,
            storage_key="pdf-key",
            size_bytes=100,
        )
        response = self.client.get(
            reverse("learning:document", kwargs={"doc_id": doc.id}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "pdf-viewer")


class LearningStorageTests(TestCase):
    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())  # nosec B108
    def test_local_save_and_open(self) -> None:
        from learning.storage import open_file, save_file

        with patch("learning.storage._minio_available", return_value=False):
            key = save_file(
                1,
                str(uuid.uuid4()),
                str(uuid.uuid4()),
                "test.md",
                io.BytesIO(b"hello"),
            )
            data = open_file(key)
        self.assertEqual(data, b"hello")
