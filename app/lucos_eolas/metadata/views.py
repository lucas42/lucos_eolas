import os
import rdflib
from urllib.parse import urlparse
from django.http import HttpResponseRedirect, HttpResponse, JsonResponse
from .models import *
from .checks import get_cached_checks
from ..lucosauth.decorators import api_auth
from django.utils import translation
from django.conf import settings
from .utils_conneg import choose_rdf_over_html, pick_best_rdf_format
from django.apps import apps
from django.core.exceptions import ObjectDoesNotExist

BASE_URL = os.environ.get("APP_ORIGIN")
EOLAS_NS = rdflib.Namespace(f"{BASE_URL}/ontology/")
DBPEDIA_NS = rdflib.Namespace("https://dbpedia.org/ontology/")
LOC_NS = rdflib.Namespace("http://www.loc.gov/mads/rdf/v1#")
WDT_NS = rdflib.Namespace("http://www.wikidata.org/prop/direct/")

_PENDING_CHECK = {
	'ok': False,
	'techDetail': 'Checks pending — background recompute not yet complete',
	'failThreshold': 3,
}

_COLD_CACHE_CHECKS = {
	'no-circular-containment': _PENDING_CHECK,
	'no-real-place-in-fictional': _PENDING_CHECK,
	'places-in-universe': _PENDING_CHECK,
	'no-invalid-wikipedia-slugs': _PENDING_CHECK,
}


def info(request):
	# Check results are precomputed by a background thread and cached.
	# On cold start (before the first recompute completes) we return pending placeholders.
	checks = get_cached_checks() or _COLD_CACHE_CHECKS
	output = {
		'system': "lucos_eolas",
		'checks': checks,
		'metrics': {},
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
	g.bind('wdt', WDT_NS)
	ontology_uri = rdflib.URIRef(f"{BASE_URL}/ontology/")
	g.add((ontology_uri, rdflib.RDF.type, rdflib.OWL.Ontology))
	g.add((EOLAS_NS.Category, rdflib.RDF.type, rdflib.OWL.Class))
	g.add((EOLAS_NS.Category, rdflib.SKOS.prefLabel, rdflib.Literal("Category", lang='en')))
	g.add((EOLAS_NS.Category, EOLAS_NS.hasCategory, EOLAS_NS[Category.META]))
	g.add((EOLAS_NS.hasCategory, rdflib.RDF.type, rdflib.OWL.ObjectProperty))
	g.add((EOLAS_NS.hasCategory, rdflib.SKOS.prefLabel, rdflib.Literal("has category", lang='en')))
	g.add((EOLAS_NS.hasCategory, rdflib.RDFS.domain, rdflib.OWL.Class))
	g.add((EOLAS_NS.hasCategory, rdflib.RDFS.range, EOLAS_NS.Category))
	g.add((EOLAS_NS.preferredIdentifier, rdflib.RDF.type, rdflib.OWL.ObjectProperty))
	g.add((EOLAS_NS.preferredIdentifier, rdflib.RDF.type, rdflib.OWL.AsymmetricProperty))
	g.add((EOLAS_NS.preferredIdentifier, rdflib.SKOS.prefLabel, rdflib.Literal("preferred identifier", lang='en')))
	g.add((EOLAS_NS.preferredIdentifier, rdflib.RDFS.comment, rdflib.Literal(
		"Subject URI declares the object URI as its preferred canonical identifier. "
		"Used by the arachne search-index ingestor to pick the primary id for merged "
		"owl:sameAs closures: arachne walks preferredIdentifier edges to find the "
		"terminal URI (the one with no outgoing edge). Asymmetric: if A preferredIdentifier B, "
		"then B preferredIdentifier A is false. Domain and range deliberately unconstrained — "
		"the predicate can apply to any URI in the estate.", lang='en')))
	for pred_uri, label in [
		(EOLAS_NS.displayBackgroundColour, "display background colour"),
		(EOLAS_NS.displayBorderColour, "display border colour"),
		(EOLAS_NS.displayTextColour, "display text colour"),
	]:
		g.add((pred_uri, rdflib.RDF.type, rdflib.OWL.DatatypeProperty))
		g.add((pred_uri, rdflib.SKOS.prefLabel, rdflib.Literal(label, lang='en')))
		g.add((pred_uri, rdflib.RDFS.domain, EOLAS_NS.Category))
		g.add((pred_uri, rdflib.RDFS.range, rdflib.XSD.string))
	for category in Category:
		category_uri = EOLAS_NS[category.value]
		g.add((category_uri, rdflib.RDF.type, EOLAS_NS.Category))
		for lang, _ in settings.LANGUAGES:
			with translation.override(lang):
				g.add((category_uri, rdflib.SKOS.prefLabel, rdflib.Literal(category.label, lang=lang)))
		g.add((category_uri, EOLAS_NS.displayBackgroundColour, rdflib.Literal(category.background)))
		g.add((category_uri, EOLAS_NS.displayBorderColour, rdflib.Literal(category.border)))
		g.add((category_uri, EOLAS_NS.displayTextColour, rdflib.Literal(category.text)))
	for model_class in apps.get_app_config('metadata').get_models():
		if (getattr(model_class, 'rdf_type', None)):
			class_uri = model_class.rdf_type
			g.add((class_uri, rdflib.RDF.type, rdflib.OWL.Class))
			for lang, _ in settings.LANGUAGES:
				with translation.override(lang):
					g.add((class_uri, rdflib.SKOS.prefLabel, rdflib.Literal(translation.gettext(model_class._meta.verbose_name), lang=lang)))
			if model_class._meta.db_table_comment:
				g.add((class_uri, rdflib.RDFS.comment, rdflib.Literal(model_class._meta.db_table_comment, lang='en')))
			class_category = getattr(model_class, 'category', None)
			if isinstance(class_category, Category):
				# Only emit a type-level hasCategory when category is a class-level constant
				# (e.g. Category.TECHNOLOGICAL on TransportMode).  Per-instance category fields
				# (CharField on PlaceType/CreativeWorkType) are descriptors, not Category enum
				# values — guarding with isinstance prevents building a garbage URI from the
				# descriptor's string representation.
				g.add((class_uri, EOLAS_NS.hasCategory, EOLAS_NS[class_category]))
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
			if (getattr(model_class, 'get_ontology_rdf', None)):
				g += model_class.get_ontology_rdf()
	return g

def _safe_local_redirect(url):
	"""Only allow redirects to relative paths on this server (no scheme or netloc)."""
	parsed = urlparse(url)
	if parsed.scheme or parsed.netloc:
		return '/'
	return url

def thing_entrypoint(request, type, pk):
	class HttpResponseSeeOther(HttpResponseRedirect):
		status_code = 303
	if choose_rdf_over_html(request):
		return HttpResponseSeeOther(_safe_local_redirect(f'/metadata/{type}/{pk}/data/'))
	else:
		# 303 See Other to the admin change endpoint for non-RDF requests
		return HttpResponseSeeOther(_safe_local_redirect(f'/metadata/{type}/{pk}/change/'))

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
	g.bind('wdt', WDT_NS)
	return HttpResponse(g.serialize(format=format), content_type=f'{content_type}; charset={settings.DEFAULT_CHARSET}')

@api_auth
def type_list(request, type):
	"""Return all items of the given type as a JSON array.

	Each item includes at minimum 'id', 'uri', and 'name', plus any
	type-specific scalar and foreign-key fields (see EolasModel.to_json).
	Returns 404 for unknown types.
	"""
	try:
		model_class = apps.get_model('metadata', type)
	except LookupError:
		return HttpResponse(status=404)
	if not hasattr(model_class, 'to_json'):
		return HttpResponse(status=404)
	items = [obj.to_json() for obj in model_class.objects.select_related().all()]
	return JsonResponse(items, safe=False)

# No auth needed — category colour data is not sensitive and is consumed by build steps
def categories_json(request):
	"""Return all categories with their display colours as a JSON array.

	Each entry has: name, slug, background, border, text.
	All three colour fields are always present (never null).
	"""
	data = []
	for category in Category:
		data.append({
			"name": category.value,
			"slug": category.value.lower(),
			"background": category.background,
			"border": category.border,
			"text": category.text,
		})
	return JsonResponse(data, safe=False)

@api_auth
def all_rdf(request):
	# Serialize all items of every type into a single RDF graph
	format, content_type = pick_best_rdf_format(request)
	g = rdflib.Graph()
	g.bind('dbpedia', DBPEDIA_NS)
	g.bind('eolas', EOLAS_NS)
	g.bind('loc', LOC_NS)
	g.bind('wdt', WDT_NS)
	g += ontology_graph()
	app_models = apps.get_app_config('metadata').get_models()
	for model_class in app_models:
		for obj in model_class.objects.all():
			g += obj.get_rdf(include_type_label=False) # Don't include type label for each item, as that'll be covered by ontology_graph()
	return HttpResponse(g.serialize(format=format), content_type=f'{content_type}; charset={settings.DEFAULT_CHARSET}')
