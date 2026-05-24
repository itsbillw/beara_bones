"""Add MariaDB FULLTEXT index for learning document search (no-op on SQLite)."""

from django.db import migrations


def add_fulltext_index(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    schema_editor.execute(
        "CREATE FULLTEXT INDEX learning_document_fts ON learning_learningdocument (title, original_filename)",
    )


def drop_fulltext_index(apps, schema_editor):
    if schema_editor.connection.vendor != "mysql":
        return
    schema_editor.execute(
        "ALTER TABLE learning_learningdocument DROP INDEX learning_document_fts",
    )


class Migration(migrations.Migration):
    dependencies = [
        ("learning", "0002_learningdocument_author_and_more"),
    ]

    operations = [
        migrations.RunPython(add_fulltext_index, drop_fulltext_index),
    ]
