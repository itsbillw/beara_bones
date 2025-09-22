from django.urls import path

from .views import index, about_me, poetry

app_name = 'home'
urlpatterns = [
    # Home page.
    path('', index, name='index'),
    path('about', about_me, name='about'),
    path('if-', poetry, name='if-')
]