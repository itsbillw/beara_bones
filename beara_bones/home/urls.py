from django.urls import path

from .views import index, beara_bones_data, about_me, poetry

app_name = 'home'
urlpatterns = [
    # Home page.
    path('', index, name='index'),
    path('data', beara_bones_data, name='data'),
    path('about', about_me, name='about'),
    path('if-', poetry, name='if-')
]