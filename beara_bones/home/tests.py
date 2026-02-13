from django.test import TestCase
from django.urls import reverse


class HomeViewTests(TestCase):
    """Smoke tests for home app views."""

    def test_index_returns_200(self) -> None:
        response = self.client.get(reverse("home:index"))
        self.assertEqual(response.status_code, 200)

    def test_data_returns_200(self) -> None:
        response = self.client.get(reverse("home:data"))
        self.assertEqual(response.status_code, 200)

    def test_about_returns_200(self) -> None:
        response = self.client.get(reverse("home:about"))
        self.assertEqual(response.status_code, 200)

    def test_poetry_returns_200(self) -> None:
        response = self.client.get(reverse("home:if-"))
        self.assertEqual(response.status_code, 200)
