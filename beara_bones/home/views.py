"""
Home app views: simple async views that render templates.

All routes are defined in home/urls.py. Names are used in templates via {% url 'home:...' %}.
"""
from django.template.response import TemplateResponse


async def index(request):
    """Landing page with quick links sidebar."""
    return TemplateResponse(request, "home/index.html")


async def beara_bones_data(request):
    """Data page (placeholder for future data/visualisation content)."""
    return TemplateResponse(request, "home/data.html")


async def about_me(request):
    """About page: site and itsbillw background."""
    return TemplateResponse(request, "home/about.html")


async def poetry(request):
    """If— by Rudyard Kipling (static poem page)."""
    return TemplateResponse(request, "home/if-.html")