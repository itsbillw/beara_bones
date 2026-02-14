"""
Home app views: landing, about, and static pages.

All routes are defined in home/urls.py. Use {% url 'home:index' %} etc. in templates.
"""

from django.template.response import TemplateResponse


async def index(request):
    """Landing page with quick links sidebar."""
    return TemplateResponse(request, "home/index.html")


async def about_me(request):
    """About page: site and itsbillw background."""
    return TemplateResponse(request, "home/about.html")


async def poetry(request):
    """If— by Rudyard Kipling (static poem page)."""
    return TemplateResponse(request, "home/if-.html")
