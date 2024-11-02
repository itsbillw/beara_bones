from django.urls import path

from .views import index, poetry

app_name = 'home'
urlpatterns = [
    # Home page.
    path('', index, name='index'),
    path('if-', poetry, name='if-')
]