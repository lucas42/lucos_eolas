from django.urls import path, re_path, include
from .metadata import views as metadata_views
from .metadata.admin import eolasadmin as admin

urlpatterns = [
	re_path(r'^_info$', metadata_views.info),
	re_path(r'^i18n/', include('django.conf.urls.i18n')),

	path('metadata/all/data/', metadata_views.all_rdf),
	# Linked Data HTTPRange-14 compliant endpoints
	re_path(r'^metadata/(?P<type>[a-z]+)/(?P<pk>(?!add)\w+)/$', metadata_views.thing_entrypoint), # Excludes the `add` path as that's used by django admin.  May cause an issue if Dzodinka is ever added to the language list, as its ISO 639-3 code is 'add'
	path('metadata/<slug:type>/<slug:pk>/data/', metadata_views.thing_data),
	path('ontology', metadata_views.ontology),

	path('', admin.urls),
	# Static files are handled by nginx at /resources, so not listed here
]