from django.contrib import admin
from .models import Place
from django.utils.html import format_html, format_html_join
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from ..lucosauth import views as auth_views

class EolasAdminSite(admin.AdminSite):
	site_title = 'LucOS Eolas'
	index_title = None
	def login(self, request):
		return auth_views.loginview(request)

eolasadmin = EolasAdminSite()

class PlaceAdmin(admin.ModelAdmin):
	filter_horizontal = ('located_in',)
	readonly_fields = ('contained_places',)

	def contained_places(self, obj):
		links = format_html_join(
			", ",
			'<a href="{}">{}</a>',
			(
				(reverse("admin:metadata_place_change", args=[p.pk]), p.name)
				for p in obj.contains.all()
			)
		)
		return links or "-"
	contained_places.short_description = _("contains")

eolasadmin.register(Place, PlaceAdmin)