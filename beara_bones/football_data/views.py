from django.template.response import TemplateResponse


async def index(request):
    return TemplateResponse(request, "football_data/index.html")