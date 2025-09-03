from django.contrib import admin
from .models import Place, PlaceType, DayOfWeek
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
	ordering = ["name"]
	filter_horizontal = ('located_in',)
	readonly_fields = ('contained_places',)
	search_fields = ['name','alternate_names']
	autocomplete_fields =  ['located_in']
	list_filter = ['type','fictional']
	show_facets = admin.ShowFacets.ALWAYS

	def contained_places(self, obj):
		# Group contained places by their type plural
		grouped = {}
		for place in obj.contains.all().select_related("type"):
			grouped.setdefault(place.type.plural, []).append(place)

		if not grouped:
			return "-"

		rows = []
		has_fictional = False

		for plural, places in sorted(grouped.items()):
			# Sort places alphabetically by name, fictional last
			sorted_places = sorted(
				places,
				key=lambda p: (p.fictional, p.name.lower())
			)

			links_list = []
			for p in sorted_places:
				if p.fictional and not obj.fictional:
					has_fictional = True
					link_html = format_html("<em>{}</em>*", p.name)
				else:
					link_html = p.name
				links_list.append(format_html('<a href="{}">{}</a>', reverse("admin:metadata_place_change", args=[p.pk]), link_html))

			links = format_html_join(", ", "{}", ((l,) for l in links_list))
			rows.append(
				format_html("<tr><td>{}</td><td>{}</td></tr>", plural.title(), links)
			)

		# Build table HTML
		table_html = format_html(
			'<table style="border-collapse: collapse;">{}</table>',
			format_html_join("", "{}", ((row,) for row in rows))
		)

		# Append native admin help text with the reusable custom class
		if has_fictional:
			table_html = format_html(
				'{}<p class="help help-inline">* Fictional places</p>',
				table_html
			)

		return table_html

	contained_places.short_description = _("contains")


eolasadmin.register(Place, PlaceAdmin)

class PlaceTypeAdmin(admin.ModelAdmin):
	ordering = ["name"]
	def save_model(self, request, obj, form, change):
		obj.name = obj.name.lower()
		obj.plural = obj.plural.lower()
		super().save_model(request, obj, form, change)

eolasadmin.register(PlaceType, PlaceTypeAdmin)

class DayOfWeekAdmin(admin.ModelAdmin):
	ordering = ["order"]

eolasadmin.register(DayOfWeek, DayOfWeekAdmin)
