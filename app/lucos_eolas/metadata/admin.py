from django.contrib import admin
from lucos_eolas.metadata.models import Place
from django.utils.html import format_html, format_html_join
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

@admin.register(Place)
class PlaceAdmin(admin.ModelAdmin):
	filter_horizontal = ('located_in',)
	readonly_fields = ('contained_places',)

	fieldsets = (
		(None, {
			'fields': ('name', 'alternate_names', 'located_in', 'contained_places')
		}),
	)

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