from django.template.response import TemplateResponse


async def index(request):
    return TemplateResponse(request, "home/index.html")

async def poetry(request):
    return TemplateResponse(request, "home/if-.html")