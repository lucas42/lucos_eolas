import os
import rdflib
from django.http import HttpResponseRedirect, HttpResponse, JsonResponse
from .models import *
from ..lucosauth.decorators import api_auth
from django.utils import translation
from django.conf import settings
from .utils_conneg import choose_rdf_over_html, pick_best_rdf_format
from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist

BASE_URL = os.environ.get("BASE_URL")
EOLAS_NS = rdflib.Namespace(f"{BASE_URL}ontology/")
DBPEDIA_NS = rdflib.Namespace("https://dbpedia.org/ontology/")
LOC_NS = rdflib.Namespace("http://www.loc.gov/mads/rdf/v1#")

def info(request):
	output = {
		'system': "lucos_eolas",
		'ci': {
			'circle': "gh/lucas42/lucos_eolas",
		},
		'icon': "/resources/icon.png",
		'network_only': True,
		'title': "Eolas",
		'show_on_homepage': True
	}
	return JsonResponse(output)

# No auth needed as ontology shouldn't contain anything sensitive
def ontology(request):
	format, content_type = pick_best_rdf_format(request)
	return HttpResponse(ontology_graph().serialize(format=format), content_type=f'{content_type}; charset={settings.DEFAULT_CHARSET}')

def ontology_graph():
	g = rdflib.Graph()
	g.bind('eolas', EOLAS_NS)
	g.bind('dbpedia', DBPEDIA_NS)
	g.bind('loc', LOC_NS)
	ontology_uri = rdflib.URIRef(f"{BASE_URL}ontology/")
	g.add((ontology_uri, rdflib.RDF.type, rdflib.OWL.Ontology))
	for model_class in apps.get_app_config('metadata').get_models():
		if (getattr(model_class, 'rdf_type', None)):
			class_uri = model_class.rdf_type
			g.add((class_uri, rdflib.RDF.type, rdflib.OWL.Class))
			for lang, _ in settings.LANGUAGES:
				with translation.override(lang):
					g.add((class_uri, rdflib.SKOS.prefLabel, rdflib.Literal(translation.gettext(model_class._meta.verbose_name), lang=lang)))
			if model_class._meta.db_table_comment:
				g.add((class_uri, rdflib.RDFS.comment, rdflib.Literal(model_class._meta.db_table_comment, lang='en')))
			for field in model_class._meta.get_fields():
				if getattr(field, 'rdf_predicate', None):
					with translation.override('en'):
						label = field.rdf_label if getattr(field, 'rdf_label', None) else field.verbose_name
						g.add((field.rdf_predicate, rdflib.SKOS.prefLabel, rdflib.Literal(label, lang='en')))
					if getattr(field, 'rdf_type', None):
						g.add((field.rdf_predicate, rdflib.RDF.type, field.rdf_type))
					g.add((field.rdf_predicate, rdflib.RDFS.domain, class_uri))
					if getattr(field, 'rdf_range', None):
						g.add((field.rdf_predicate, rdflib.RDFS.range, field.rdf_range))
					if getattr(field, 'db_comment', None):
						g.add((field.rdf_predicate, rdflib.RDFS.comment, rdflib.Literal(field.db_comment, lang='en')))
					if getattr(field, 'rdf_inverse_predicate', None):
						g.add((field.rdf_predicate, rdflib.OWL.inverseOf, field.rdf_inverse_predicate))
						g.add((field.rdf_inverse_predicate, rdflib.RDF.type, rdflib.OWL.ObjectProperty)) # Only Object Properities can have an inverse
						inverse_label = field.rdf_inverse_label if getattr(field, 'rdf_inverse_label', None) else field.related_query_name()
						g.add((field.rdf_inverse_predicate, rdflib.SKOS.prefLabel, rdflib.Literal(inverse_label, lang='en')))
						g.add((field.rdf_inverse_predicate, rdflib.RDFS.range, class_uri))
						if getattr(field, 'rdf_range', None):
							g.add((field.rdf_inverse_predicate, rdflib.RDFS.domain, field.rdf_range))
	return g

def thing_entrypoint(request, type, pk):
	class HttpResponseSeeOther(HttpResponseRedirect):
		status_code = 303
	if choose_rdf_over_html(request):
		return HttpResponseSeeOther(f'/metadata/{type}/{pk}/data/')
	else:
		# 303 See Other to the admin change endpoint for non-RDF requests
		return HttpResponseSeeOther(f'/metadata/{type}/{pk}/change/')

@api_auth
def thing_data(request, type, pk):
	format, content_type = pick_best_rdf_format(request)
	try:
		model_class = apps.get_model('metadata', type)
		obj = model_class.objects.get(pk=pk)
	except (ObjectDoesNotExist, LookupError):
		return HttpResponse(status=404)
	g = obj.get_rdf(include_type_label=True)
	g.bind('dbpedia', DBPEDIA_NS)
	g.bind('eolas', EOLAS_NS)
	g.bind('loc', LOC_NS)
	return HttpResponse(g.serialize(format=format), content_type=f'{content_type}; charset={settings.DEFAULT_CHARSET}')

@api_auth
def all_rdf(request):
	# Serialize all items of every type into a single RDF graph
	format, content_type = pick_best_rdf_format(request)
	g = rdflib.Graph()
	g.bind('dbpedia', DBPEDIA_NS)
	g.bind('eolas', EOLAS_NS)
	g.bind('loc', LOC_NS)
	g += ontology_graph()
	app_models = apps.get_app_config('metadata').get_models()
	for model_class in app_models:
		for obj in model_class.objects.all():
			g += obj.get_rdf(include_type_label=False) # Don't include type label for each item, as that'll be covered by ontology_graph()
	return HttpResponse(g.serialize(format=format), content_type=f'{content_type}; charset={settings.DEFAULT_CHARSET}')
