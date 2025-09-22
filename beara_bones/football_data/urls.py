from django.urls import path

from .views import index

app_name = 'football_data'
urlpatterns = [
    # Home page.
    path('football/', index, name='index'),
]