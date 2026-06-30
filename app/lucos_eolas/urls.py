from django.urls import path, re_path, include
from .metadata import views as metadata_views
from .metadata.admin import eolasadmin as admin

urlpatterns = [
	re_path(r'^_info$', metadata_views.info),
	re_path(r'^i18n/', include('django.conf.urls.i18n')),

	path('metadata/categories.json', metadata_views.categories_json),
	path('metadata/names', metadata_views.batch_names),
	path('metadata/all/data/', metadata_views.all_rdf),
	path('metadata/<slug:type>/list/', metadata_views.type_list),
	path('api/metadata/<slug:type>/', metadata_views.thing_create),
	# Linked Data HTTPRange-14 compliant endpoints
	re_path(r'^metadata/(?P<type>[a-z]+)/(?P<pk>(?!add/)[\w-]+)/$', metadata_views.thing_entrypoint), # Excludes the exact `add/` path (used by django admin) while allowing hyphens for e.g. ISO 639 constructed-language codes (art-x-ewok).  `(?!add$)` wouldn't work here because the full URL contains a trailing slash after the pk, so `$` never matches — `(?!add/)` precisely excludes only the exact pk "add".
	path('metadata/<slug:type>/<slug:pk>/data/', metadata_views.thing_data),
	path('ontology', metadata_views.ontology),

	path('', admin.urls),
	# Static files are handled by nginx at /resources, so not listed here
]