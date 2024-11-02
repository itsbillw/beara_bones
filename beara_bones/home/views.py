from django.shortcuts import render


def index(request):
    return render(request, "home/index.html")

def poetry(request):
    return render(request, "home/if-.html")