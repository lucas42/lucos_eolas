from django.contrib import admin
from django.urls import path
from lucos_eolas.lucosauth import views as auth_views

admin.site.login = auth_views.loginview

urlpatterns = [
    path('', admin.site.urls),
    # Static files are handled by nginx at /resources, so not listed here
]
