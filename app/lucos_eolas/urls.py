from django.contrib import admin
from django.urls import path, re_path
from lucos_eolas.lucosauth import views as auth_views
from lucos_eolas.metadata import views as metadata_views

admin.site.login = auth_views.loginview
admin.site.site_title = 'LucOS Eolas'

urlpatterns = [
    re_path(r'^_info$', metadata_views.info),
    path('', admin.site.urls),
    # Static files are handled by nginx at /resources, so not listed here
]
