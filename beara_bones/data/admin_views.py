"""
Admin-only views to trigger football pipeline refresh and rebuild from MinIO.
"""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.management import call_command
from django.http import HttpResponseRedirect
from django.shortcuts import render
from django.urls import reverse

from data.pipeline_service import enqueue_pipeline_refresh


@staff_member_required
def pipeline_control(request):
    """Show a simple page with Refresh and Rebuild buttons."""
    return render(request, "admin/data/pipeline_control.html")


@staff_member_required
def pipeline_refresh(request):
    """POST only: start run_football_pipeline in background."""
    if request.method != "POST":
        return HttpResponseRedirect(reverse("data:admin_pipeline"))
    result = enqueue_pipeline_refresh(source="admin_button")
    if result["status"] == "already_running":
        messages.warning(
            request,
            "Pipeline already in progress. Wait or remove the lock file.",
        )
    else:
        messages.success(request, result.get("message", "Pipeline refresh started."))
    return HttpResponseRedirect(reverse("data:admin_pipeline"))


@staff_member_required
def pipeline_rebuild(request):
    """POST only: run rebuild_football_from_minio (blocking)."""
    if request.method != "POST":
        return HttpResponseRedirect(reverse("data:admin_pipeline"))
    from pathlib import Path

    from django.conf import settings

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
