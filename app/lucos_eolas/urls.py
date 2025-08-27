from django.urls import re_path, include
from django.contrib import admin
from django.urls import path
from django.shortcuts import redirect
from django.utils.http import urlencode
from lucos_eolas.lucosauth import views as auth_views



"""Send all admin login attempts straight to /accounts/login."""
def direct_admin_login(request, extra_context=None):
    params = urlencode({"next": request.GET.get("next", "/admin/")})
    return redirect(f"/accounts/login/?{params}")

admin.site.login = direct_admin_login

urlpatterns = [
    path('admin/', admin.site.urls),
    re_path(r'^accounts/login/', auth_views.loginview),
    # Static files are handled by nginx so not listed here
]
