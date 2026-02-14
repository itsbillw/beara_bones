"""
URL routing for the data app.

Included from project urls.py at '' so paths are at site root.
Use {% url 'data:data' %}, {% url 'data:data_fragment' %}, {% url 'data:data_refresh' %} in templates.
"""
from django.urls import path

from .views import data_page, data_fragment, data_refresh

app_name = "data"
urlpatterns = [
    path("data", data_page, name="data"),
    path("data/fragment", data_fragment, name="data_fragment"),
    path("data/refresh", data_refresh, name="data_refresh"),
]
