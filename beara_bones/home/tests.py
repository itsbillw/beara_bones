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
