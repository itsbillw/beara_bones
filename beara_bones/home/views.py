from django.template.response import TemplateResponse


async def index(request):
    return TemplateResponse(request, "home/index.html")

async def beara_bones_data(request):
    return TemplateResponse(request, "home/data.html")

async def about_me(request):
    return TemplateResponse(request, "home/about.html")

async def poetry(request):
    return TemplateResponse(request, "home/if-.html")