from django.shortcuts import render

def index(request):
    """The home page for thatsmoreofit"""
    return render(request, 'main/index.html')