from django.contrib import admin
from django.urls import path, re_path, include
from .metadata import views as metadata_views
from .metadata.admin import eolasadmin as admin

urlpatterns = [
    re_path(r'^_info$', metadata_views.info),
    re_path (r'^i18n/' ,include('django.conf.urls.i18n')),
    path('', admin.urls),
    # Static files are handled by nginx at /resources, so not listed here
]
