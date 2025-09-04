from django.urls import path, re_path, include
from .metadata import views as metadata_views
from .metadata.admin import eolasadmin as admin

urlpatterns = [
	re_path(r'^_info$', metadata_views.info),
	re_path(r'^i18n/', include('django.conf.urls.i18n')),

	# Linked Data HTTPRange-14 compliant endpoints
	path('metadata/<slug:type>/<int:pk>/', metadata_views.thing_entrypoint),
	path('metadata/<slug:type>/<int:pk>/data/', metadata_views.thing_data),
	path('metadata/all/data/', metadata_views.all_rdf),

	path('', admin.urls),
	# Static files are handled by nginx at /resources, so not listed here
]