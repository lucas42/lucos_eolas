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
					label = field.rdf_label if getattr(field, 'rdf_label', None) else field.name
					g.add((field.rdf_predicate, rdflib.SKOS.prefLabel, rdflib.Literal(label, lang='en')))
					if getattr(field, 'rdf_type', None):
						g.add((field.rdf_predicate, rdflib.RDF.type, field.rdf_type))
					g.add((field.rdf_predicate, rdflib.RDFS.domain, class_uri))
					if getattr(field, 'rdf_range', None):
						g.add((field.rdf_predicate, rdflib.RDFS.range, field.rdf_range))
					if getattr(field, 'db_comment', None):
						g.add((field.rdf_predicate, rdflib.RDFS.comment, rdflib.Literal(field.db_comment, lang='en')))
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
	g = get_rdf_by_item(model_class, obj, include_type_label=True)
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
			g += get_rdf_by_item(model_class, obj, include_type_label=False) # Don't include type label for each item, as that'll be covered by ontology_graph()
	return HttpResponse(g.serialize(format=format), content_type=f'{content_type}; charset={settings.DEFAULT_CHARSET}')

def get_rdf_by_item(model_class, item, include_type_label):
	if model_class in custom_model_handlers:
		return custom_model_handlers[model_class](item, include_type_label)
	else:
		(_, g) = object_to_rdf(item, include_type_label)
		return g

def object_to_rdf(item, include_type_label):
	uri = rdflib.URIRef(item.get_absolute_url())
	g = rdflib.Graph()
	if (hasattr(item, 'rdf_type')):
		g.add((uri, rdflib.RDF.type, item.rdf_type))
		if include_type_label:
			for lang, _ in settings.LANGUAGES:
				with translation.override(lang):
					g.add((item.rdf_type, rdflib.SKOS.prefLabel, rdflib.Literal(translation.gettext(item._meta.verbose_name), lang=lang)))
	for field in item._meta.get_fields():
		if hasattr(field, 'get_rdf'):
			g += field.get_rdf(item)
	return (uri, g)

def place_to_rdf(place, include_type_label):
	place_uri = rdflib.URIRef(place.get_absolute_url())
	g = rdflib.Graph()
	for alt in place.alternate_names:
		g.add((place_uri, rdflib.RDFS.label, rdflib.Literal(alt)))
	type_uri = rdflib.URIRef(place.type.get_absolute_url())
	g.add((place_uri, rdflib.RDF.type, type_uri))
	if include_type_label:
		g += placetype_to_rdf(place.type, include_type_label)
	g.add((place_uri, EOLAS_NS.isFictional, rdflib.Literal(place.fictional)))
	for container in place.located_in.all():
		container_uri = rdflib.URIRef(container.get_absolute_url())
		g.add((place_uri, rdflib.SDO.containedInPlace, container_uri))
	return g

def placetype_to_rdf(placetype, include_type_label):
	(type_uri, g) = object_to_rdf(placetype, include_type_label)
	g.add((type_uri, rdflib.RDFS.subClassOf, rdflib.SDO.Place))
	return g

def festival_to_rdf(festival, include_type_label):
	(festival_uri, g) = object_to_rdf(festival, include_type_label)
	# Represent startDay as a blank node
	if festival.day_of_month is not None or festival.month is not None:
		start_day_bnode = rdflib.BNode()
		g.add((festival_uri, EOLAS_NS.festivalStartsOn, start_day_bnode))
		if festival.day_of_month is not None:
			g.add((start_day_bnode, rdflib.TIME.day, rdflib.Literal(festival.day_of_month)))
		if festival.month is not None:
			month_uri = rdflib.URIRef(festival.month.get_absolute_url())
			g.add((start_day_bnode, rdflib.TIME.MonthOfYear, month_uri))
	return g

custom_model_handlers = {
	PlaceType: placetype_to_rdf,
	Place: place_to_rdf,
	Festival: festival_to_rdf,
}