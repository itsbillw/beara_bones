"""Smoke tests for home app: each view returns 200."""

from django.test import TestCase
from django.urls import reverse


class HomeViewTests(TestCase):
    """Home, About, and If— poem pages load successfully."""

    def test_index_returns_200(self) -> None:
        response = self.client.get(reverse("home:index"))
        self.assertEqual(response.status_code, 200)

    def test_about_returns_200(self) -> None:
        response = self.client.get(reverse("home:about"))
        self.assertEqual(response.status_code, 200)

    def test_poetry_returns_200(self) -> None:
        response = self.client.get(reverse("home:if-"))
        self.assertEqual(response.status_code, 200)

    def test_index_has_theme_support(self) -> None:
        response = self.client.get(reverse("home:index"))
        self.assertContains(response, 'data-theme-choice="light"')
        self.assertContains(response, 'data-theme-choice="dark"')
        self.assertContains(response, "itsbillw-theme")

    def test_about_has_theme_support(self) -> None:
        response = self.client.get(reverse("home:about"))
        self.assertContains(response, 'data-theme-choice="light"')
        self.assertContains(response, 'data-theme-choice="dark"')
        self.assertContains(response, "home/js/theme.js")

    def test_poetry_has_theme_support(self) -> None:
        response = self.client.get(reverse("home:if-"))
        self.assertContains(response, 'data-theme-choice="light"')
        self.assertContains(response, 'data-theme-choice="dark"')
        self.assertContains(response, "dataset.theme")

    def test_base_template_sets_theme_cookie_inline(self) -> None:
        response = self.client.get(reverse("home:index"))
        self.assertContains(response, "itsbillw-theme=")
        self.assertContains(response, "document.documentElement.dataset.theme")
