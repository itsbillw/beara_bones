"""
Admin-only views to trigger football pipeline refresh and rebuild from MinIO.
"""

import subprocess  # nosec B404
from pathlib import Path

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse


@staff_member_required
def pipeline_control(request):
    """Show a simple page with Refresh and Rebuild buttons."""
    return render(request, "admin/data/pipeline_control.html")


@staff_member_required
def pipeline_refresh(request):
    """POST only: start run_football_pipeline in background."""
    if request.method != "POST":
        return HttpResponseRedirect(reverse("data:admin_pipeline"))
    repo_root = Path(settings.BASE_DIR).parent
    lock_file = repo_root / "data" / "football" / ".refresh.lock"
    if lock_file.exists():
        messages.warning(
            request,
            "Pipeline already in progress. Wait or remove the lock file.",
        )
        return HttpResponseRedirect(reverse("data:admin_pipeline"))
    subprocess.Popen(  # nosec B603 B607
        ["uv", "run", "python", "beara_bones/manage.py", "run_football_pipeline"],
        cwd=str(repo_root),
        start_new_session=True,
    )
    messages.success(request, "Pipeline refresh started in the background.")
    return HttpResponseRedirect(reverse("data:admin_pipeline"))


@staff_member_required
def pipeline_rebuild(request):
    """POST only: run rebuild_football_from_minio (blocking)."""
    if request.method != "POST":
        return HttpResponseRedirect(reverse("data:admin_pipeline"))
    from django.core.management import call_command

    repo_root = Path(settings.BASE_DIR).parent
    lock_file = repo_root / "data" / "football" / ".refresh.lock"
    if lock_file.exists():
        messages.warning(
            request,
            "Pipeline already in progress. Wait or remove the lock file.",
        )
        return HttpResponseRedirect(reverse("data:admin_pipeline"))
    try:
        call_command("rebuild_football_from_minio")
        messages.success(request, "Rebuild from MinIO completed.")
    except Exception as e:
        messages.error(request, str(e))
    return HttpResponseRedirect(reverse("data:admin_pipeline"))
