"""Zip import/export helpers for the learning vault."""

from __future__ import annotations

import io
import zipfile
from pathlib import PurePosixPath
from typing import TYPE_CHECKING, BinaryIO

from django.utils.text import slugify

from .forms import ALLOWED_EXTENSIONS
from .models import LearningDirectory

if TYPE_CHECKING:
    from django.contrib.auth.models import AbstractBaseUser


def _safe_zip_path(name: str) -> PurePosixPath | None:
    """Return a safe posix path inside the zip, or None if invalid."""
    path = PurePosixPath(name.replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts:
        return None
    return path


def extract_zip_to_directory(
    user: AbstractBaseUser,
    parent: LearningDirectory,
    zip_file: BinaryIO,
    save_document_fn,
) -> tuple[int, int]:
    """Extract allowed files from zip into directory tree. Returns (dirs, docs) counts."""
    dirs_created = 0
    docs_created = 0
    dir_cache: dict[str, LearningDirectory] = {"": parent}

    with zipfile.ZipFile(zip_file) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            safe = _safe_zip_path(info.filename)
            if safe is None:
                continue
            ext = "." + safe.suffix.lstrip(".").lower() if safe.suffix else ""
            if ext not in ALLOWED_EXTENSIONS:
                continue

            parts = list(safe.parts)
            filename = parts[-1]
            dir_parts = parts[:-1]

            current = parent
            path_key = ""
            for part in dir_parts:
                path_key = f"{path_key}/{part}" if path_key else part
                if path_key not in dir_cache:
                    subdir = LearningDirectory.objects.create(
                        owner=user,
                        name=part,
                        slug=slugify(part) or "folder",
                        parent=current,
                    )
                    dir_cache[path_key] = subdir
                    dirs_created += 1
                    current = subdir
                else:
                    current = dir_cache[path_key]

            data = zf.read(info)
            buffer: io.BytesIO = io.BytesIO(data)
            setattr(buffer, "name", filename)
            setattr(buffer, "size", len(data))
            save_document_fn(user, current, buffer)
            docs_created += 1

    return dirs_created, docs_created


def build_directory_zip(directory: LearningDirectory) -> io.BytesIO:
    """Build a zip archive of a directory and its contents recursively."""
    from .storage import open_file

    buffer = io.BytesIO()
    base_name = directory.name

    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:

        def add_directory(dir_obj: LearningDirectory, prefix: str) -> None:
            for sub in dir_obj.children.filter(owner=dir_obj.owner).order_by("name"):
                sub_prefix = f"{prefix}{sub.name}/"
                zf.writestr(sub_prefix, "")
                add_directory(sub, sub_prefix)
            for doc in dir_obj.documents.filter(owner=dir_obj.owner).order_by("title"):
                try:
                    data = open_file(doc.storage_key)
                except FileNotFoundError:
                    continue
                arcname = f"{prefix}{doc.original_filename}"
                zf.writestr(arcname, data)

        zf.writestr(f"{base_name}/", "")
        add_directory(directory, f"{base_name}/")

    buffer.seek(0)
    return buffer
