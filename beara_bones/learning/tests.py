"""Tests for the learning vault app."""

from __future__ import annotations

import io
import json
import tempfile
import uuid
import zipfile
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from learning.models import (
    LearningActivity,
    LearningDirectory,
    LearningDocument,
    LearningInvite,
    LearningStarred,
    LearningTag,
)
from learning.tree_utils import active_directory_path, build_directory_tree

User = get_user_model()


class LearningAuthTests(TestCase):
    def test_vault_redirects_when_anonymous(self) -> None:
        response = self.client.get(reverse("learning:vault"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/learning/login/", response.url)

    def test_login_page_accessible(self) -> None:
        response = self.client.get(reverse("learning:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Remember me")

    def test_remember_me_extends_session(self) -> None:
        User.objects.create_user("remember", "r@example.com", "pass")
        response = self.client.post(
            reverse("learning:login"),
            {
                "username": "remember",
                "password": "pass",  # pragma: allowlist secret
                "remember_me": True,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertGreater(self.client.session.get_expiry_age(), 86400)

    def test_logout_get_not_allowed(self) -> None:
        response = self.client.get(reverse("learning:logout"))
        self.assertEqual(response.status_code, 405)

    def test_logout_post_redirects_to_vault_then_login(self) -> None:
        user = User.objects.create_user("logoutuser", "l@example.com", "pass")
        self.client.force_login(user)
        response = self.client.post(reverse("learning:logout"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("learning:vault"))
        follow = self.client.get(reverse("learning:vault"))
        self.assertEqual(follow.status_code, 302)
        self.assertIn("/learning/login/", follow.url)


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

    def test_search_returns_only_owned_documents(self) -> None:
        self.client.force_login(self.user_b)
        response = self.client.get(reverse("learning:search"), {"q": "Alice"})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Alice Note")


class LearningTreeUtilsTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("treeuser", "t@example.com", "pass")
        self.root = LearningDirectory.objects.create(
            owner=self.user,
            name="Root",
            slug="root",
        )
        self.child = LearningDirectory.objects.create(
            owner=self.user,
            name="Child",
            slug="child",
            parent=self.root,
        )

    def test_build_directory_tree_nests_children(self) -> None:
        dirs = list(LearningDirectory.objects.filter(owner=self.user))
        tree = build_directory_tree(dirs)
        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0].directory.id, self.root.id)
        self.assertEqual(len(tree[0].children), 1)
        self.assertEqual(tree[0].children[0].directory.id, self.child.id)

    def test_active_directory_path_includes_ancestors(self) -> None:
        path = active_directory_path(self.child)
        self.assertEqual(path, {self.root.id, self.child.id})


class LearningVaultTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("vaultuser", "v@example.com", "pass")
        self.client.force_login(self.user)
        cache.clear()

    def test_vault_renders_view_toggle_and_search(self) -> None:
        response = self.client.get(reverse("learning:vault"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "learning-view-toggle")
        self.assertContains(response, "learning-search-input")
        self.assertContains(response, "learning-tree")

    def test_vault_shows_recent_section(self) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        doc = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Recent Doc",
            original_filename="recent.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="key",
            size_bytes=10,
        )
        LearningActivity.objects.create(user=self.user, document=doc)
        response = self.client.get(reverse("learning:vault"))
        self.assertContains(response, "Recent")
        self.assertContains(response, "Recent Doc")

    def test_vault_shows_starred_section(self) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        doc = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Starred Doc",
            original_filename="star.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="key",
            size_bytes=10,
        )
        LearningStarred.objects.create(user=self.user, document=doc)
        response = self.client.get(reverse("learning:vault"))
        self.assertContains(response, "Starred")
        self.assertContains(response, "Starred Doc")

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
        doc = LearningDocument.objects.get(owner=self.user)
        self.assertTrue(doc.content_hash)

    @patch("learning.views.save_file", return_value="users/1/dir/doc_test.md")
    def test_upload_ajax_returns_json(self, _mock_save: object) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        upload = SimpleUploadedFile("note.md", b"# One", content_type="text/markdown")
        response = self.client.post(
            reverse("learning:upload"),
            {"directory_id": str(directory.id), "file": upload},
            HTTP_X_REQUESTED_WITH="XMLHttpRequest",
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["count"], 1)

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
        self.assertTrue(
            LearningActivity.objects.filter(user=self.user, document=doc).exists(),
        )

    @patch("learning.storage.open_file")
    @patch("learning.views.open_file")
    def test_wikilink_resolves(
        self,
        mock_views_open: MagicMock,
        mock_storage_open: MagicMock,
    ) -> None:
        cache.clear()
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

        def side_effect(key: str) -> bytes:
            return {
                "source-key": b"See [[Target Note]] for details.",
                "target-key": b"# Target",
            }[key]

        mock_views_open.side_effect = side_effect
        mock_storage_open.side_effect = side_effect
        response = self.client.get(
            reverse("learning:document", kwargs={"doc_id": source.id}),
        )
        self.assertEqual(response.status_code, 200)
        expected_url = reverse("learning:document", kwargs={"doc_id": target.id})
        self.assertContains(response, expected_url)

    @patch("learning.storage.open_file")
    @patch("learning.views.open_file")
    def test_backlinks_shown(
        self,
        mock_views_open: MagicMock,
        mock_storage_open: MagicMock,
    ) -> None:
        cache.clear()
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

        def side_effect(key: str) -> bytes:
            return {
                "source-key": b"See [[Target Note]] for details.",
                "target-key": b"# Target body",
            }[key]

        mock_views_open.side_effect = side_effect
        mock_storage_open.side_effect = side_effect
        response = self.client.get(
            reverse("learning:document", kwargs={"doc_id": target.id}),
        )
        self.assertContains(response, "Linked from")
        self.assertContains(response, source.title)

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
        self.assertContains(response, "pdf-toolbar")

    def test_pdf_progress_saved(self) -> None:
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
        url = reverse("learning:document_progress", kwargs={"doc_id": doc.id})
        response = self.client.post(
            url,
            data=json.dumps({"page": 5}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        activity = LearningActivity.objects.get(user=self.user, document=doc)
        self.assertEqual(activity.last_page, 5)

    def test_search_finds_document(self) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Unique Title XYZ",
            original_filename="unique.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="key",
            size_bytes=10,
        )
        response = self.client.get(reverse("learning:search"), {"q": "Unique"})
        self.assertContains(response, "Unique Title XYZ")

    def test_type_filter_pdf_only(self) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="PDF Doc",
            original_filename="doc.pdf",
            content_type=LearningDocument.ContentType.PDF,
            storage_key="pdf",
            size_bytes=10,
        )
        LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="MD Doc",
            original_filename="doc.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="md",
            size_bytes=10,
        )
        response = self.client.get(
            reverse("learning:directory", kwargs={"dir_id": directory.id}),
            {"type": "pdf"},
        )
        self.assertContains(response, "PDF Doc")
        self.assertNotContains(response, "MD Doc")

    def test_tag_filter(self) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        tag = LearningTag.objects.create(owner=self.user, name="verbs", slug="verbs")
        tagged = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Tagged",
            original_filename="tagged.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="tagged",
            size_bytes=10,
        )
        tagged.tags.add(tag)
        LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Untagged",
            original_filename="plain.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="plain",
            size_bytes=10,
        )
        response = self.client.get(
            reverse("learning:directory", kwargs={"dir_id": directory.id}),
            {"tag": "verbs"},
        )
        self.assertContains(response, "Tagged")
        self.assertNotContains(response, "Untagged")

    def test_document_meta_update(self) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        doc = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Old Title",
            original_filename="note.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="key",
            size_bytes=10,
        )
        response = self.client.post(
            reverse("learning:document_meta", kwargs={"doc_id": doc.id}),
            {
                "title": "New Title",
                "language": "es",
                "topic": "verbs",
                "author": "Author",
                "difficulty": "beginner",
                "tag_names": "grammar, verbs",
            },
        )
        self.assertEqual(response.status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.title, "New Title")
        self.assertEqual(doc.language, "es")
        self.assertEqual(doc.tags.count(), 2)

    def test_star_toggle(self) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        doc = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Doc",
            original_filename="doc.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="key",
            size_bytes=10,
        )
        url = reverse("learning:document_star", kwargs={"doc_id": doc.id})
        response = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(json.loads(response.content)["starred"])
        response = self.client.post(url, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertFalse(json.loads(response.content)["starred"])

    def test_document_star_htmx_returns_partial(self) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        doc = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Doc",
            original_filename="doc.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="key",
            size_bytes=10,
        )
        url = reverse("learning:document_star", kwargs={"doc_id": doc.id})
        response = self.client.post(url, HTTP_HX_REQUEST="true")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, f"doc-row-{doc.id}")
        self.assertContains(response, "bi-star-fill")

    def test_document_meta_htmx_returns_204(self) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs-meta",
        )
        doc = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Old Title",
            original_filename="note.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="key",
            size_bytes=10,
        )
        response = self.client.post(
            reverse("learning:document_meta", kwargs={"doc_id": doc.id}),
            {
                "title": "HTMX Title",
                "language": "en",
                "topic": "topic",
                "author": "Author",
                "difficulty": "beginner",
                "tag_names": "one",
            },
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 204)
        doc.refresh_from_db()
        self.assertEqual(doc.title, "HTMX Title")

    @patch("learning.views._save_uploaded_document")
    def test_upload_hx_request_returns_file_rows(
        self,
        mock_save: MagicMock,
    ) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Uploads",
            slug="uploads",
        )
        doc = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Uploaded",
            original_filename="new.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="upload-key",
            size_bytes=12,
        )
        mock_save.return_value = (doc, None)
        upload = SimpleUploadedFile("new.md", b"# New", content_type="text/markdown")
        response = self.client.post(
            reverse("learning:upload"),
            {"directory_id": str(directory.id), "file": upload},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Uploaded")
        self.assertContains(response, f"doc-row-{doc.id}")

    @patch("learning.views.overwrite_file", return_value=12)
    def test_markdown_edit_saves(self, _mock_overwrite: object) -> None:
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
            size_bytes=10,
        )
        response = self.client.post(
            reverse("learning:document_edit", kwargs={"doc_id": doc.id}),
            {"content": "# Updated\n\nNew body."},
        )
        self.assertEqual(response.status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.size_bytes, 12)

    @patch("learning.views.open_file", return_value=b"---\ntitle: Test\n---\n\n# Body")
    def test_frontmatter_displayed(self, _mock_open: object) -> None:
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
            size_bytes=10,
        )
        response = self.client.get(
            reverse("learning:document", kwargs={"doc_id": doc.id}),
        )
        self.assertContains(response, "learning-frontmatter")

    def test_move_document(self) -> None:
        src = LearningDirectory.objects.create(owner=self.user, name="Src", slug="src")
        dst = LearningDirectory.objects.create(owner=self.user, name="Dst", slug="dst")
        doc = LearningDocument.objects.create(
            owner=self.user,
            directory=src,
            title="Doc",
            original_filename="doc.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="stable-key",
            size_bytes=10,
        )
        response = self.client.post(
            reverse("learning:document_move", kwargs={"doc_id": doc.id}),
            {"directory_id": str(dst.id)},
        )
        self.assertEqual(response.status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.directory_id, dst.id)
        self.assertEqual(doc.storage_key, "stable-key")

    def test_rename_directory(self) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Old",
            slug="old",
        )
        response = self.client.post(
            reverse("learning:directory_rename", kwargs={"dir_id": directory.id}),
            {"name": "New Name"},
        )
        self.assertEqual(response.status_code, 302)
        directory.refresh_from_db()
        self.assertEqual(directory.name, "New Name")

    def test_move_directory_into_descendant_blocked(self) -> None:
        parent = LearningDirectory.objects.create(
            owner=self.user,
            name="Parent",
            slug="parent",
        )
        child = LearningDirectory.objects.create(
            owner=self.user,
            name="Child",
            slug="child",
            parent=parent,
        )
        response = self.client.post(
            reverse("learning:directory_move", kwargs={"dir_id": parent.id}),
            {"directory_id": str(child.id)},
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        parent.refresh_from_db()
        self.assertIsNone(parent.parent_id)
        self.assertContains(response, "subfolder")

    @patch("learning.views.save_file", return_value="users/1/dir/doc_test.md")
    def test_duplicate_hash_warning(self, _mock_save: object) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        content = b"same content"
        upload1 = SimpleUploadedFile("one.md", content, content_type="text/markdown")
        self.client.post(
            reverse("learning:upload"),
            {"directory_id": str(directory.id), "file": upload1},
        )
        upload2 = SimpleUploadedFile("two.md", content, content_type="text/markdown")
        response = self.client.post(
            reverse("learning:upload"),
            {"directory_id": str(directory.id), "file": upload2},
            follow=True,
        )
        self.assertContains(response, "duplicate")

    @patch("learning.views.save_file", return_value="users/1/dir/imported.md")
    @patch("learning.views._maybe_generate_thumbnail")
    def test_zip_import(self, _thumb: object, _save: object) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as zf:
            zf.writestr("sub/note.md", b"# Imported")
        buffer.seek(0)
        upload = SimpleUploadedFile(
            "vault.zip",
            buffer.read(),
            content_type="application/zip",
        )
        response = self.client.post(
            reverse("learning:directory_import_zip", kwargs={"dir_id": directory.id}),
            {"file": upload},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(LearningDocument.objects.filter(owner=self.user).count(), 1)
        self.assertTrue(
            LearningDirectory.objects.filter(owner=self.user, name="sub").exists(),
        )

    @patch("learning.storage.open_file", return_value=b"# Exported")
    def test_zip_export(self, _mock_open: object) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Export",
            slug="export",
        )
        LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Note",
            original_filename="note.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="key",
            size_bytes=10,
        )
        response = self.client.get(
            reverse("learning:directory_export_zip", kwargs={"dir_id": directory.id}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/zip")

    def test_cached_render_markdown_caches(self) -> None:
        from learning.markdown_utils import cached_render_markdown

        cache.clear()
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
        with patch(
            "learning.markdown_utils.md_lib.markdown",
            return_value="<p>Cached</p>",
        ) as mock_md:
            cached_render_markdown(doc, "# Body", [], {})
            cached_render_markdown(doc, "# Body", [], {})
            self.assertEqual(mock_md.call_count, 1)

    @patch("learning.views.open_file", return_value=b"%PDF-1.4 fake")
    def test_split_view_note_param(self, _mock_open: object) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Papers",
            slug="papers",
        )
        pdf = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Paper",
            original_filename="paper.pdf",
            content_type=LearningDocument.ContentType.PDF,
            storage_key="pdf-key",
            size_bytes=100,
        )
        note = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Notes",
            original_filename="notes.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="note-key",
            size_bytes=10,
        )
        response = self.client.get(
            reverse("learning:document", kwargs={"doc_id": pdf.id}),
            {"note": str(note.id)},
        )
        self.assertContains(response, "learning-split-view")


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

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())  # nosec B108
    def test_thumbnail_save(self) -> None:
        from learning.storage import open_file, save_thumbnail

        with patch("learning.storage._minio_available", return_value=False):
            key = save_thumbnail(str(uuid.uuid4()), b"\x89PNG")
            data = open_file(key)
        self.assertEqual(data, b"\x89PNG")


class LearningMarkdownUtilsTests(TestCase):
    """Unit tests for markdown rendering helpers."""

    def setUp(self) -> None:
        self.user = User.objects.create_user("mduser", "md@example.com", "pass")

    def test_split_and_strip_frontmatter(self) -> None:
        from learning.markdown_utils import split_frontmatter, strip_frontmatter

        meta, body = split_frontmatter("---\ntitle: Hi\n---\n\n# Body")
        self.assertEqual(meta["title"], "Hi")
        self.assertIn("# Body", body)
        self.assertEqual(strip_frontmatter("---\nx: 1\n---\nText"), "Text")

    def test_resolve_wikilinks_resolves_and_marks_missing(self) -> None:
        from learning.markdown_utils import resolve_wikilinks

        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        doc = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Target",
            original_filename="target.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="k",
            size_bytes=1,
        )
        url = reverse("learning:document", kwargs={"doc_id": doc.id})
        html = resolve_wikilinks(
            "See [[Target]] and [[Missing]]",
            {"target": url},
            {"target": "Preview text"},
        )
        self.assertIn(f'href="{url}"', html)
        self.assertIn("wikilink-missing", html)
        self.assertIn('data-bs-content="Preview text"', html)

    def test_preview_snippet_truncates_long_text(self) -> None:
        from learning.markdown_utils import _preview_snippet

        long_text = "word " * 80
        snippet = _preview_snippet(long_text, limit=40)
        self.assertLessEqual(len(snippet), 40)
        self.assertTrue(snippet.endswith("…"))

    def test_render_markdown_sanitizes_output(self) -> None:
        from learning.markdown_utils import render_markdown

        html = render_markdown("<script>x</script>\n\n**bold**", [])
        self.assertNotIn("<script>", html)
        self.assertIn("<strong>bold</strong>", html)

    def test_render_markdown_cached_uses_cache(self) -> None:
        from learning.markdown_utils import render_markdown_cached

        cache.clear()
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
            storage_key="k",
            size_bytes=1,
        )
        with patch(
            "learning.markdown_utils.render_markdown",
            return_value="<p>Cached</p>",
        ) as mock_render:
            render_markdown_cached(doc, [], "# Body")
            render_markdown_cached(doc, [], "# Body")
            mock_render.assert_called_once()

    def test_build_preview_index_from_raw_contents(self) -> None:
        from learning.markdown_utils import build_preview_index

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
            storage_key="k",
            size_bytes=1,
        )
        previews = build_preview_index([doc], {str(doc.id): "# Hello world"})
        self.assertIn("note", previews)

    @patch("learning.storage.open_file", return_value=b"Link [[Target]]")
    def test_find_backlinks(self, _mock_open: object) -> None:
        from learning.markdown_utils import find_backlinks

        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        target = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Target",
            original_filename="target.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="target",
            size_bytes=1,
        )
        source = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Source",
            original_filename="source.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="source",
            size_bytes=1,
        )
        backlinks = find_backlinks(target, [source, target])
        self.assertEqual(backlinks, [source])

    def test_find_backlinks_with_contents(self) -> None:
        from learning.markdown_utils import find_backlinks_with_contents

        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        target = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Target",
            original_filename="target.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="target",
            size_bytes=1,
        )
        source = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Source",
            original_filename="source.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="source",
            size_bytes=1,
        )
        raw = {str(source.id): "See [[Target]]"}
        backlinks = find_backlinks_with_contents(target, [source, target], raw)
        self.assertEqual(backlinks, [source])

    @patch("learning.storage.open_file", side_effect=FileNotFoundError)
    def test_get_user_markdown_raw_contents_skips_missing(
        self,
        _mock_open: object,
    ) -> None:
        from learning.markdown_utils import get_user_markdown_raw_contents

        cache.clear()
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
            storage_key="missing",
            size_bytes=1,
            content_hash="abc",
        )
        raw = get_user_markdown_raw_contents(self.user.id, [doc])
        self.assertEqual(raw, {})


class LearningTemplateTagTests(TestCase):
    def test_filesizeformat_bytes(self) -> None:
        from learning.templatetags.learning_tags import filesizeformat_bytes

        self.assertEqual(filesizeformat_bytes(0), "0 B")
        self.assertEqual(filesizeformat_bytes(512), "512 B")
        self.assertEqual(filesizeformat_bytes(2048), "2.0 KB")
        self.assertEqual(filesizeformat_bytes(5 * 1024 * 1024), "5.0 MB")
        self.assertEqual(filesizeformat_bytes(True), "—")
        self.assertEqual(filesizeformat_bytes("nope"), "—")
        self.assertEqual(filesizeformat_bytes(-1), "—")


class LearningThumbnailTests(TestCase):
    def test_generate_pdf_thumbnail_success(self) -> None:
        import sys

        from learning.thumbnail_utils import generate_pdf_thumbnail

        mock_pdfium = MagicMock()
        mock_page = MagicMock()
        mock_bitmap = MagicMock()
        mock_pil = MagicMock()
        mock_pdf = MagicMock()
        mock_pdf.__len__.return_value = 1
        mock_pdf.__getitem__.return_value = mock_page
        mock_pdfium.PdfDocument.return_value = mock_pdf
        mock_page.render.return_value = mock_bitmap
        mock_bitmap.to_pil.return_value = mock_pil

        def save_png(buffer, format="PNG"):
            buffer.write(b"\x89PNG")

        mock_pil.save.side_effect = save_png
        with patch.dict(sys.modules, {"pypdfium2": mock_pdfium}):
            png = generate_pdf_thumbnail(b"%PDF-1.4")
        self.assertEqual(png, b"\x89PNG")

    def test_generate_pdf_thumbnail_empty_pdf(self) -> None:
        import sys

        from learning.thumbnail_utils import generate_pdf_thumbnail

        mock_pdfium = MagicMock()
        mock_pdf = MagicMock()
        mock_pdf.__len__.return_value = 0
        mock_pdfium.PdfDocument.return_value = mock_pdf
        with patch.dict(sys.modules, {"pypdfium2": mock_pdfium}):
            self.assertIsNone(generate_pdf_thumbnail(b"%PDF-1.4"))

    def test_generate_pdf_thumbnail_handles_render_error(self) -> None:
        import sys

        from learning.thumbnail_utils import generate_pdf_thumbnail

        mock_pdfium = MagicMock()
        mock_pdfium.PdfDocument.side_effect = RuntimeError("bad pdf")
        with (
            patch.dict(sys.modules, {"pypdfium2": mock_pdfium}),
            patch("learning.thumbnail_utils.logger.warning") as mock_warning,
        ):
            self.assertIsNone(generate_pdf_thumbnail(b"not-a-pdf"))
        mock_warning.assert_called_once()


class LearningStorageExtendedTests(TestCase):
    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())  # nosec B108
    def test_overwrite_file_updates_bytes(self) -> None:
        from learning.storage import open_file, overwrite_file, save_file

        with patch("learning.storage._minio_available", return_value=False):
            key = save_file(
                1,
                str(uuid.uuid4()),
                str(uuid.uuid4()),
                "a.md",
                io.BytesIO(b"v1"),
            )
            size = overwrite_file(key, io.BytesIO(b"updated"))
            self.assertEqual(size, 7)
            self.assertEqual(open_file(key), b"updated")

    @override_settings(MEDIA_ROOT=tempfile.mkdtemp())  # nosec B108
    def test_delete_file_removes_local_copy(self) -> None:
        from learning.storage import delete_file, open_file, save_file

        with patch("learning.storage._minio_available", return_value=False):
            key = save_file(
                1,
                str(uuid.uuid4()),
                str(uuid.uuid4()),
                "del.md",
                io.BytesIO(b"x"),
            )
            delete_file(key)
            with self.assertRaises(FileNotFoundError):
                open_file(key)

    @patch("football.minio_utils.get_bytes_object", return_value=b"remote")
    @patch("football.minio_utils.get_minio_client")
    @patch("learning.storage._minio_available", return_value=True)
    def test_open_file_reads_from_minio(
        self,
        _mock_avail: MagicMock,
        mock_client_fn: MagicMock,
        _mock_get_bytes: MagicMock,
    ) -> None:
        from learning.storage import open_file

        mock_client_fn.return_value = MagicMock()
        data = open_file("users/1/x/y.md")
        self.assertEqual(data, b"remote")

    @patch("football.minio_utils.get_minio_client")
    @patch("learning.storage._minio_available", return_value=True)
    def test_delete_file_removes_minio_object(
        self,
        _mock_avail: MagicMock,
        mock_client_fn: MagicMock,
    ) -> None:
        from learning.storage import delete_file

        mock_client = MagicMock()
        mock_client_fn.return_value = mock_client
        delete_file("users/1/x/y.md")
        mock_client.remove_object.assert_called_once()


class LearningThemeTests(TestCase):
    def test_login_page_has_theme_support(self) -> None:
        response = self.client.get(reverse("learning:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-theme-choice="light"')
        self.assertContains(response, 'data-theme-choice="dark"')

    def test_join_page_has_theme_support(self) -> None:
        staff = User.objects.create_superuser("staff2", "s2@example.com", "pass")
        invite = LearningInvite.objects.create(
            email="join@example.com",
            created_by=staff,
        )
        response = self.client.get(
            reverse("learning:join", kwargs={"token": invite.token}),
        )
        self.assertContains(response, 'data-theme-choice="light"')
        self.assertContains(response, 'data-theme-choice="dark"')


class LearningViewExtendedTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user("extuser", "ext@example.com", "pass")
        self.client.force_login(self.user)

    def test_note_titles_api(self) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Alpha",
            original_filename="alpha.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="a",
            size_bytes=1,
        )
        response = self.client.get(reverse("learning:note_titles_api"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["titles"], ["Alpha"])

    @patch("learning.views.save_file", return_value="users/1/dir/new.md")
    def test_create_note_from_template(self, _mock_save: object) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        response = self.client.post(
            reverse("learning:create_note"),
            {
                "directory_id": str(directory.id),
                "title": "My Note",
                "template": "blank",
            },
        )
        self.assertEqual(response.status_code, 302)
        doc = LearningDocument.objects.get(owner=self.user, title="My Note")
        self.assertIn("/edit/", response.url)
        self.assertEqual(doc.content_type, LearningDocument.ContentType.MARKDOWN)

    @patch("learning.views.delete_file")
    def test_document_delete(self, mock_delete: MagicMock) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        doc = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Delete Me",
            original_filename="del.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="del-key",
            size_bytes=1,
        )
        response = self.client.post(
            reverse("learning:document_delete", kwargs={"doc_id": doc.id}),
        )
        self.assertEqual(response.status_code, 302)
        self.assertFalse(LearningDocument.objects.filter(id=doc.id).exists())
        mock_delete.assert_called()

    def test_document_rename(self) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        doc = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Old",
            original_filename="old.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="k",
            size_bytes=1,
        )
        response = self.client.post(
            reverse("learning:document_rename", kwargs={"doc_id": doc.id}),
            {"title": "Renamed"},
        )
        self.assertEqual(response.status_code, 302)
        doc.refresh_from_db()
        self.assertEqual(doc.title, "Renamed")

    @patch("learning.views.open_file", return_value=b"# Raw")
    def test_document_edit_get(self, _mock_open: object) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        doc = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Edit",
            original_filename="edit.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="k",
            size_bytes=1,
        )
        response = self.client.get(
            reverse("learning:document_edit", kwargs={"doc_id": doc.id}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "# Raw")

    @patch("learning.views.open_file", return_value=b"%PDF-1.4")
    def test_document_raw_pdf(self, _mock_open: object) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        doc = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Paper",
            original_filename="paper.pdf",
            content_type=LearningDocument.ContentType.PDF,
            storage_key="pdf",
            size_bytes=10,
        )
        response = self.client.get(
            reverse("learning:document_raw", kwargs={"doc_id": doc.id}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")

    @patch("learning.views.open_file")
    @patch("learning.views.generate_pdf_thumbnail", return_value=b"\x89PNG")
    @patch("learning.views.save_thumbnail", return_value="thumbnails/x.png")
    def test_document_thumbnail_generates_on_demand(
        self,
        _mock_save: MagicMock,
        _mock_thumb: MagicMock,
        mock_open: MagicMock,
    ) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        doc = LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Paper",
            original_filename="paper.pdf",
            content_type=LearningDocument.ContentType.PDF,
            storage_key="pdf-key",
            size_bytes=10,
        )

        def side_effect(key: str) -> bytes:
            if key.startswith("thumbnails/"):
                return b"\x89PNG"
            return b"%PDF-1.4"

        mock_open.side_effect = side_effect
        response = self.client.get(
            reverse("learning:document_thumbnail", kwargs={"doc_id": doc.id}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "image/png")

    def test_directory_move_success(self) -> None:
        child = LearningDirectory.objects.create(
            owner=self.user,
            name="Child",
            slug="child",
        )
        target = LearningDirectory.objects.create(
            owner=self.user,
            name="Target",
            slug="target",
        )
        response = self.client.post(
            reverse("learning:directory_move", kwargs={"dir_id": child.id}),
            {"directory_id": str(target.id)},
        )
        self.assertEqual(response.status_code, 302)
        child.refresh_from_db()
        self.assertEqual(child.parent_id, target.id)

    def test_vault_sort_by_date(self) -> None:
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="docs",
        )
        LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Zebra",
            original_filename="z.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="z",
            size_bytes=1,
        )
        response = self.client.get(
            reverse("learning:directory", kwargs={"dir_id": directory.id}),
            {"sort": "date"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Zebra")


class SearchUtilsTests(TestCase):
    """Document search helpers."""

    def setUp(self) -> None:
        self.user = User.objects.create_user("searcher", "s@example.com", "pass")

    def test_search_empty_query_returns_none(self) -> None:
        from learning.search_utils import search_documents

        self.assertEqual(search_documents(self.user, "").count(), 0)
        self.assertEqual(search_documents(self.user, "   ").count(), 0)

    @patch("learning.search_utils.connection")
    def test_search_mysql_uses_fulltext(self, mock_connection: MagicMock) -> None:
        from learning.search_utils import search_documents

        mock_connection.vendor = "mysql"
        directory = LearningDirectory.objects.create(
            owner=self.user,
            name="Docs",
            slug="search-docs",
        )
        LearningDocument.objects.create(
            owner=self.user,
            directory=directory,
            title="Grammar guide",
            original_filename="grammar.md",
            content_type=LearningDocument.ContentType.MARKDOWN,
            storage_key="grammar",
            size_bytes=10,
        )
        qs = search_documents(self.user, "grammar")
        self.assertEqual(str(qs.query).lower().count("match"), 1)
