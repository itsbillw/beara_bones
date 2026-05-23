"""Learning app URL configuration."""

from django.urls import path

from . import views

app_name = "learning"

urlpatterns = [
    path("", views.vault, name="vault"),
    path("login/", views.LearningLoginView.as_view(), name="login"),
    path("logout/", views.LearningLogoutView.as_view(), name="logout"),
    path("join/<str:token>/", views.join, name="join"),
    path("d/<uuid:dir_id>/", views.directory_detail, name="directory"),
    path("doc/<uuid:doc_id>/", views.document_view, name="document"),
    path("doc/<uuid:doc_id>/raw/", views.document_raw, name="document_raw"),
    path("upload/", views.upload, name="upload"),
    path("mkdir/", views.mkdir, name="mkdir"),
    path("doc/<uuid:doc_id>/delete/", views.document_delete, name="document_delete"),
]
