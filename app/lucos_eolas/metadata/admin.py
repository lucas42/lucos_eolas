from django.contrib import admin
from .models import *
from .signals import metadata_post_delete
from django.utils.html import format_html, format_html_join
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from ..lucosauth import views as auth_views
from django.apps import apps
from django.contrib.admin.sites import AlreadyRegistered
from django.contrib import messages
from django.db.models.signals import post_delete
from django.shortcuts import render
from loganne import updateLoganne
from urllib.parse import urlencode

class EolasAdminSite(admin.AdminSite):
	site_title = 'LucOS Eolas'
	index_title = None
	def login(self, request):
		return auth_views.loginview(request)
eolasadmin = EolasAdminSite()

def merge_entities(modeladmin, request, queryset):
	"""Admin action: merge selected entities, firing a Loganne event per source."""
	if queryset.count() < 2:
		modeladmin.message_user(request, _("Select at least 2 entities to merge."), level=messages.ERROR)
		return

	if 'apply_merge' in request.POST:
		target_id = request.POST.get('target_id')
		target = queryset.filter(pk=target_id).first()
		if target is None:
			modeladmin.message_user(request, _("Please select a valid merge target."), level=messages.ERROR)
			return

		sources = queryset.exclude(pk=target.pk)
		merged_count = sources.count()
		item_type = queryset.model._meta.verbose_name.title()

		for source in sources:
			updateLoganne(
				type="itemMerged",
				humanReadable=f'{item_type} "{source}" merged into "{target}"',
				url=target.get_absolute_url(),
				sourceUri=source.get_absolute_url(),
				targetUri=target.get_absolute_url(),
				itemType=item_type,
			)
			post_delete.disconnect(metadata_post_delete, sender=queryset.model)
			try:
				source.delete()
			finally:
				post_delete.connect(metadata_post_delete, sender=queryset.model)

		modeladmin.message_user(
			request,
			_(f'Merged {merged_count} {"entity" if merged_count == 1 else "entities"} into "{target}".'),
		)
		return

	return render(request, 'admin/metadata/merge_entities.html', {
		'title': _('Select merge target'),
		'queryset': queryset,
		'opts': modeladmin.model._meta,
		'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
	})

merge_entities.short_description = _('Merge selected entities')


class EolasModelAdmin(admin.ModelAdmin):
	actions = ['merge_entities']
	merge_entities = staticmethod(merge_entities)

	def get_fields(self, request, obj=None):
		all_fields = [
			f.name for f in self.model._meta.get_fields()
			if f.editable and not f.auto_created and f.name not in ["name", "wikipedia_slug"]
		]
		all_fields.insert(0, "name") # Make sure name is always first, regardless of where it is defined
		all_fields.append("wikipedia_slug") # Move wiki slug to the end of the list
		return all_fields
	def changeform_view(self, request, object_id=None, form_url="", extra_context=None):
		extra_context = extra_context or {}
		obj = self.get_object(request, object_id)
		if obj and hasattr(obj, "get_absolute_url"):
			absolute_object_url = request.build_absolute_uri(
				obj.get_absolute_url()
			)
			extra_context["arachne_url"] = (
				"https://arachne.l42.eu/explore/item?"
				+ urlencode({"uri": absolute_object_url})
			)
		return super().changeform_view(
			request, object_id, form_url, extra_context=extra_context
		)

class PlaceAdmin(EolasModelAdmin):
	filter_horizontal = ('contained_in', 'partially_contained_in', 'territory_of', 'bounds',)
	readonly_fields = ('contained_places',)
	search_fields = ['name','alternate_names']
	autocomplete_fields =  ['contained_in', 'partially_contained_in', 'territory_of', 'bounds']
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

class PlaceTypeAdmin(EolasModelAdmin):
	def save_model(self, request, obj, form, change):
		obj.name = obj.name.lower()
		obj.plural = obj.plural.lower()
		super().save_model(request, obj, form, change)
eolasadmin.register(PlaceType, PlaceTypeAdmin)

class MonthAdmin(EolasModelAdmin):
	list_filter = ['calendar']
	show_facets = admin.ShowFacets.ALWAYS
eolasadmin.register(Month, MonthAdmin)

class LanguageFamilyAdmin(EolasModelAdmin):
	def save_model(self, request, obj, form, change):
		obj.code = obj.code.lower()
		super().save_model(request, obj, form, change)
eolasadmin.register(LanguageFamily, LanguageFamilyAdmin)

class LanguageAdmin(EolasModelAdmin):
	list_filter = ['family']
	show_facets = admin.ShowFacets.ALWAYS
	search_fields = ['name', 'alternate_names']
	autocomplete_fields = ['indigenous_to', 'widely_spoken_in']
	def save_model(self, request, obj, form, change):
		obj.code = obj.code.lower()
		super().save_model(request, obj, form, change)
eolasadmin.register(Language, LanguageAdmin)

class EthnicGroupAdmin(EolasModelAdmin):
	search_fields = ['name', 'alternate_names']
	autocomplete_fields = ['heritage_language', 'indigenous_to']
eolasadmin.register(EthnicGroup, EthnicGroupAdmin)

class CreativeWorkTypeAdmin(EolasModelAdmin):
	def save_model(self, request, obj, form, change):
		obj.name = obj.name.lower()
		obj.plural = obj.plural.lower()
		super().save_model(request, obj, form, change)
eolasadmin.register(CreativeWorkType, CreativeWorkTypeAdmin)

class CreativeWorkAdmin(EolasModelAdmin):
	list_filter = ['type']
	show_facets = admin.ShowFacets.ALWAYS
eolasadmin.register(CreativeWork, CreativeWorkAdmin)

class TransportModeAdmin(EolasModelAdmin):
	def save_model(self, request, obj, form, change):
		obj.name = obj.name.lower()
		obj.plural = obj.plural.lower()
		super().save_model(request, obj, form, change)
eolasadmin.register(TransportMode, TransportModeAdmin)

class VehicleAdmin(EolasModelAdmin):
	search_fields = ['name', 'alternate_names']
	list_filter = ['type', 'fictional']
	show_facets = admin.ShowFacets.ALWAYS
eolasadmin.register(Vehicle, VehicleAdmin)

class PersonAdmin(EolasModelAdmin):
	search_fields = ['name', 'alternate_names']
eolasadmin.register(Person, PersonAdmin)

class FestivalPeriodInline(admin.TabularInline):
	model = FestivalPeriod
	extra = 1
	fields = ['name', 'start_day', 'start_month', 'duration_days']

class FestivalAdmin(EolasModelAdmin):
	inlines = [FestivalPeriodInline]
eolasadmin.register(Festival, FestivalAdmin)

## Register all the other models without any bespoke config
app_models = apps.get_app_config('metadata').get_models()
for model in app_models:
	try:
		eolasadmin.register(model, EolasModelAdmin)
	except AlreadyRegistered:
		pass