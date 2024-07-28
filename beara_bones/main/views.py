"""
Views config for beara_bones project.
"""

from django.shortcuts import render


# Needless docstring, thanks pylint
def index(request):
    """The home page for thatsmoreofit"""
    return render(request, "main/index.html")
