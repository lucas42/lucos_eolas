import os
import rdflib
from django.http import HttpResponseRedirect, HttpResponse, JsonResponse
from .models import *
from ..lucosauth.decorators import api_auth
from django.utils import translation
from django.conf import settings
from .utils_conneg import choose_rdf_over_html, pick_best_rdf_format
from django.apps import apps

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
	ontology_uri = rdflib.URIRef(f"{BASE_URL}ontology/")
	g.add((ontology_uri, rdflib.RDF.type, rdflib.OWL.Ontology))
	# Classes
	for class_name, doc in [
		('Calendar', 'A system for organizing dates.'),
		('Festival', 'A recurring celebration or event.'),
		('Memory', 'A remembered event or fact.'),
		('Number', 'A numeric concept.'),
		('Historical Event', 'A notable thing that happened in the past.'),
		('Weather', 'A short term state of the atmosphere.'),
	]:
		class_uri = EOLAS_NS[class_name.replace(" ", "")]
		g.add((class_uri, rdflib.RDF.type, rdflib.OWL.Class))
		for lang, _ in settings.LANGUAGES:
			with translation.override(lang):
				g.add((class_uri, rdflib.SKOS.prefLabel, rdflib.Literal(translation.gettext(class_name), lang=lang)))
		g.add((class_uri, rdflib.RDFS.comment, rdflib.Literal(doc, lang='en')))
	# Properties: (name, property type, comment, domain, range)
	props = [
		('isFictional', rdflib.OWL.DatatypeProperty, 'Whether a place is fictional (boolean).', rdflib.SDO.Place, rdflib.XSD.boolean),
		('orderInWeek', rdflib.OWL.DatatypeProperty, 'Order of day in the week (integer).', rdflib.TIME.DayOfWeek, rdflib.XSD.integer),
		('calendar', rdflib.OWL.ObjectProperty, 'Calendar this month belongs to.', rdflib.TIME.MonthOfYear, EOLAS_NS.Calendar),
		('orderInCalendar', rdflib.OWL.DatatypeProperty, 'Order of month in calendar (integer).', rdflib.TIME.MonthOfYear, rdflib.XSD.integer),
		('festivalStartsOn', rdflib.OWL.ObjectProperty, 'When a festival starts.', EOLAS_NS.Festival, rdflib.TIME.DateTimeDescription),
		('occuredOn', rdflib.OWL.ObjectProperty, 'The point in time a memory is recalling.', EOLAS_NS.Memory, rdflib.TIME.DateTimeDescription),
		('numericValue', rdflib.OWL.DatatypeProperty, 'The (approximate) numeric value for a number (decimal).', EOLAS_NS.Number, rdflib.XSD.decimal),
	]
	for name, prop_type, comment, domain, rng in props:
		prop_uri = EOLAS_NS[name]
		g.add((prop_uri, rdflib.RDF.type, prop_type))
		g.add((prop_uri, rdflib.SKOS.prefLabel, rdflib.Literal(name, lang='en')))
		g.add((prop_uri, rdflib.RDFS.comment, rdflib.Literal(comment, lang='en')))
		g.add((prop_uri, rdflib.RDFS.domain, domain))
		g.add((prop_uri, rdflib.RDFS.range, rng))

	# Schema.org ontology is huge and importing it all slows down queries.  Instead just add the bits we use here.
	g.add((rdflib.SDO.Place, rdflib.RDF.type, rdflib.RDFS.Class))
	g.add((rdflib.SDO.Place, rdflib.RDFS.subClassOf, rdflib.SDO.Thing))
	g.add((rdflib.SDO.Place, rdflib.RDFS.label, rdflib.Literal("Place")))
	g.add((rdflib.SDO.Place, rdflib.RDFS.comment, rdflib.Literal("Entities that have a somewhat fixed, physical extension.")))

	g.add((rdflib.SDO.CreativeWork, rdflib.RDF.type, rdflib.RDFS.Class))
	g.add((rdflib.SDO.CreativeWork, rdflib.RDFS.subClassOf, rdflib.SDO.Thing))
	g.add((rdflib.SDO.CreativeWork, rdflib.RDFS.label, rdflib.Literal("CreativeWork")))
	g.add((rdflib.SDO.CreativeWork, rdflib.RDFS.comment, rdflib.Literal("The most generic kind of creative work, including books, movies, photographs, software programs, etc.")))

	g.add((rdflib.SDO.Thing, rdflib.RDF.type, rdflib.RDFS.Class))
	g.add((rdflib.SDO.Thing, rdflib.RDFS.label, rdflib.Literal("Thing")))
	g.add((rdflib.SDO.Thing, rdflib.RDFS.comment, rdflib.Literal("The most generic type of item.")))

	# Label missing from dbpedia ontology
	g.add((DBPEDIA_NS.MeanOfTransportation, rdflib.RDFS.label, rdflib.Literal("Mode of Transport", lang='en')))
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
	g = to_rdf_by_model[model_class](obj)

	## For any types in the EOLAS_NS namespace, also return the type's prefLabel, to make it easier for lucos_arachne to add a type in its search index
	if type == 'place':
		g += placetype_to_rdf(obj.type)
	elif type == 'calendar':
		g.add((EOLAS_NS['Calendar'], rdflib.SKOS.prefLabel, rdflib.Literal("Calendar")))
	elif type == 'festival':
		g.add((EOLAS_NS['Festival'], rdflib.SKOS.prefLabel, rdflib.Literal("Festival")))
	elif type == 'memory':
		g.add((EOLAS_NS['Memory'], rdflib.SKOS.prefLabel, rdflib.Literal("Memory")))
	elif type == 'number':
		g.add((EOLAS_NS['Number'], rdflib.SKOS.prefLabel, rdflib.Literal("Number")))
	elif type == 'historicalevent':
		g.add((EOLAS_NS['HistoricalEvent'], rdflib.SKOS.prefLabel, rdflib.Literal("Historical Event")))
	elif type == 'weather':
		g.add((EOLAS_NS['Weather'], rdflib.SKOS.prefLabel, rdflib.Literal("Weather")))
	return HttpResponse(g.serialize(format=format), content_type=f'{content_type}; charset={settings.DEFAULT_CHARSET}')

@api_auth
def all_rdf(request):
	# Serialize all items of every type into a single RDF graph
	format, content_type = pick_best_rdf_format(request)
	g = rdflib.Graph()
	g.bind('eolas', EOLAS_NS)
	g.bind('loc', LOC_NS)
	g += ontology_graph()
	for model_class in to_rdf_by_model:
		for obj in model_class.objects.all():
			g += to_rdf_by_model[model_class](obj)
	return HttpResponse(g.serialize(format=format), content_type=f'{content_type}; charset={settings.DEFAULT_CHARSET}')

def object_to_rdf(item):
	uri = rdflib.URIRef(item.get_absolute_url())
	g = rdflib.Graph()
	g.add((uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(item))))
	g.add((uri, rdflib.RDFS.label, rdflib.Literal(item.name)))
	if hasattr(item, 'alternate_names'):
		for alt in item.alternate_names:
			g.add((uri, rdflib.RDFS.label, rdflib.Literal(alt)))
	return (uri, g)

def place_to_rdf(place):
	(place_uri, g) = object_to_rdf(place)
	type_uri = rdflib.URIRef(place.type.get_absolute_url())
	g.bind('eolas', EOLAS_NS)
	g.add((place_uri, rdflib.RDF.type, type_uri))
	g.add((place_uri, EOLAS_NS.isFictional, rdflib.Literal(place.fictional)))
	for container in place.located_in.all():
		container_uri = rdflib.URIRef(container.get_absolute_url())
		g.add((place_uri, rdflib.SDO.containedInPlace, container_uri))
	return g

def placetype_to_rdf(placetype):
	(type_uri, g) = object_to_rdf(placetype)
	g.add((type_uri, rdflib.RDFS.subClassOf, rdflib.SDO.Place))
	return g

def dayofweek_to_rdf(day):
	(day_uri, g) = object_to_rdf(day)
	g.bind('eolas', EOLAS_NS)
	g.add((day_uri, rdflib.RDF.type, rdflib.TIME.DayOfWeek))
	g.add((day_uri, EOLAS_NS.orderInWeek, rdflib.Literal(day.order)))
	return g

def calendar_to_rdf(calendar):
	(calendar_uri, g) = object_to_rdf(calendar)
	g.bind('eolas', EOLAS_NS)
	g.add((calendar_uri, rdflib.RDF.type, EOLAS_NS.Calendar))
	return g

def month_to_rdf(month):
	(month_uri, g) = object_to_rdf(month)
	calendar_uri = rdflib.URIRef(month.calendar.get_absolute_url())
	g.bind('eolas', EOLAS_NS)
	g.add((month_uri, rdflib.RDF.type, rdflib.TIME.MonthOfYear))
	g.add((month_uri, EOLAS_NS.calendar, calendar_uri))
	g.add((month_uri, EOLAS_NS.orderInCalendar, rdflib.Literal(month.order_in_calendar)))
	return g

def festival_to_rdf(festival):
	(festival_uri, g) = object_to_rdf(festival)
	g.bind('eolas', EOLAS_NS)
	g.add((festival_uri, rdflib.RDF.type, EOLAS_NS.Festival))
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

def memory_to_rdf(memory):
	(memory_uri, g) = object_to_rdf(memory)
	g.bind('eolas', EOLAS_NS)
	g.add((memory_uri, rdflib.RDF.type, EOLAS_NS.Memory))
	if memory.description:
		g.add((memory_uri, rdflib.DC.description, rdflib.Literal(memory.description)))
	if memory.year is not None:
		datetime_bnode = rdflib.BNode()
		g.add((memory_uri, EOLAS_NS.occuredOn, datetime_bnode))
		g.add((datetime_bnode, rdflib.TIME.year, rdflib.Literal(memory.year)))
	return g

def number_to_rdf(number):
	(number_uri, g) = object_to_rdf(number)
	g.bind('eolas', EOLAS_NS)
	g.add((number_uri, rdflib.RDF.type, EOLAS_NS.Number))
	if number.value is not None:
		g.add((number_uri, EOLAS_NS.numericValue, rdflib.Literal(number.value, datatype=rdflib.XSD.decimal)))
	return g

def transportmode_to_rdf(transportmode):
	(transport_uri, g) = object_to_rdf(transportmode)
	g.bind('dbpedia', DBPEDIA_NS)
	g.add((transport_uri, rdflib.RDF.type, DBPEDIA_NS.MeanOfTransportation))
	return g

def languagefamily_to_rdf(languagefamily):
	(languagefamily_uri, g) = object_to_rdf(languagefamily)
	g.bind('loc', LOC_NS)
	g.add((languagefamily_uri, rdflib.RDF.type, rdflib.URIRef("http://id.loc.gov/vocabulary/iso639-5/iso639-5_Language")))
	if languagefamily.parent:
		g.add((languagefamily_uri, LOC_NS.hasBroaderAuthority, rdflib.URIRef(f"http://id.loc.gov/vocabulary/iso639-5/{languagefamily.parent.pk}")))
	return g

def language_to_rdf(language):
	(language_uri, g) = object_to_rdf(language)
	g.bind('loc', LOC_NS)
	g.add((language_uri, rdflib.RDF.type, LOC_NS.Language))
	g.add((language_uri, LOC_NS.hasBroaderExternalAuthority, rdflib.URIRef(language.family.get_absolute_url())))
	return g

def historicalevent_to_rdf(historicalevent):
	(historicalevent_uri, g) = object_to_rdf(historicalevent)
	g.bind('eolas', EOLAS_NS)
	g.add((historicalevent_uri, rdflib.RDF.type, EOLAS_NS.HistoricalEvent))
	if historicalevent.wikipedia_slug:
		g.add((historicalevent_uri, rdflib.OWL.sameAs, rdflib.URIRef(f"http://dbpedia.org/resource/{historicalevent.wikipedia_slug}")))
	if historicalevent.year is not None:
		datetime_bnode = rdflib.BNode()
		g.add((historicalevent_uri, EOLAS_NS.occuredOn, datetime_bnode))
		g.add((datetime_bnode, rdflib.TIME.year, rdflib.Literal(historicalevent.year)))
	return g

def weather_to_rdf(weather):
	(weather_uri, g) = object_to_rdf(weather)
	g.bind('eolas', EOLAS_NS)
	g.add((weather_uri, rdflib.RDF.type, EOLAS_NS.Weather))
	return g

def ethnicgroup_to_rdf(transportmode):
	(ethnicgroup_uri, g) = object_to_rdf(transportmode)
	g.bind('dbpedia', DBPEDIA_NS)
	g.add((ethnicgroup_uri, rdflib.RDF.type, DBPEDIA_NS.EthnicGroup))
	return g

to_rdf_by_model = {
	PlaceType: placetype_to_rdf,
	Place: place_to_rdf,
	DayOfWeek: dayofweek_to_rdf,
	Calendar: calendar_to_rdf,
	Month: month_to_rdf,
	Festival: festival_to_rdf,
	Memory: memory_to_rdf,
	Number: number_to_rdf,
	TransportMode: transportmode_to_rdf,
	LanguageFamily: languagefamily_to_rdf,
	Language: language_to_rdf,
	HistoricalEvent: historicalevent_to_rdf,
	Weather: weather_to_rdf,
	EthnicGroup: ethnicgroup_to_rdf,
}