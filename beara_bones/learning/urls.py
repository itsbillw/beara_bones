"""Learning app URL configuration."""

from django.urls import path

from . import views

app_name = "learning"

urlpatterns = [
    path("", views.vault, name="vault"),
    path("search/", views.search, name="search"),
    path("login/", views.LearningLoginView.as_view(), name="login"),
    path("logout/", views.LearningLogoutView.as_view(), name="logout"),
    path("join/<str:token>/", views.join, name="join"),
    path("d/<uuid:dir_id>/", views.directory_detail, name="directory"),
    path(
        "d/<uuid:dir_id>/export/",
        views.directory_export_zip,
        name="directory_export_zip",
    ),
    path(
        "d/<uuid:dir_id>/import/",
        views.directory_import_zip,
        name="directory_import_zip",
    ),
    path("d/<uuid:dir_id>/rename/", views.directory_rename, name="directory_rename"),
    path("d/<uuid:dir_id>/move/", views.directory_move, name="directory_move"),
    path("doc/<uuid:doc_id>/", views.document_view, name="document"),
    path("doc/<uuid:doc_id>/raw/", views.document_raw, name="document_raw"),
    path(
        "doc/<uuid:doc_id>/thumb/",
        views.document_thumbnail,
        name="document_thumbnail",
    ),
    path(
        "doc/<uuid:doc_id>/progress/",
        views.document_progress,
        name="document_progress",
    ),
    path("doc/<uuid:doc_id>/edit/", views.document_edit, name="document_edit"),
    path("doc/<uuid:doc_id>/meta/", views.document_meta, name="document_meta"),
    path("doc/<uuid:doc_id>/star/", views.document_star, name="document_star"),
    path("doc/<uuid:doc_id>/move/", views.document_move, name="document_move"),
    path("doc/<uuid:doc_id>/rename/", views.document_rename, name="document_rename"),
    path("doc/<uuid:doc_id>/delete/", views.document_delete, name="document_delete"),
    path("upload/", views.upload, name="upload"),
    path("mkdir/", views.mkdir, name="mkdir"),
    path("create-note/", views.create_note, name="create_note"),
    path("api/note-titles/", views.note_titles_api, name="note_titles_api"),
]
