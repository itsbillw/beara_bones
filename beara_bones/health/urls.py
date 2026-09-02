"""URL routing for the health app."""

from django.urls import path

from health import views

app_name = "health"
urlpatterns = [
    path("health", views.health_page, name="health"),
    path("health/cards", views.health_cards, name="cards"),
    path("health/charts", views.health_charts, name="charts"),
]
