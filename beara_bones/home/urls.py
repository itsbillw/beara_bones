"""
URL routing for the home app.

Included from project urls.py at '' so these paths are at the site root.
Use {% url 'home:index' %}, etc., in templates.
"""
from django.urls import path

from .views import index, beara_bones_data, about_me, poetry, data_refresh

app_name = "home"
urlpatterns = [
    path("", index, name="index"),
    path("data", beara_bones_data, name="data"),
    path("data/refresh", data_refresh, name="data_refresh"),
    path("about", about_me, name="about"),
    path("if-", poetry, name="if-"),  # Poem page; name has hyphen to match title.
]