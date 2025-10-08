import os
import rdflib
from django.http import HttpResponseRedirect, HttpResponse, JsonResponse
from .models import Place, PlaceType, DayOfWeek, Calendar, Month, Festival, Memory, Number, TransportMode, LanguageFamily, Language, HistoricalEvent
from ..lucosauth.decorators import api_auth
from django.utils import translation
from django.conf import settings
from .utils_conneg import choose_rdf_over_html, pick_best_rdf_format

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
	if type == 'place':
		try:
			obj = Place.objects.get(pk=pk)
		except Place.DoesNotExist:
			return HttpResponse(status=404)
		g = place_to_rdf(obj)
		g += placetype_to_rdf(obj.type)
	elif type == 'placetype':
		try:
			obj = PlaceType.objects.get(pk=pk)
		except PlaceType.DoesNotExist:
			return HttpResponse(status=404)
		g = placetype_to_rdf(obj)
	elif type == 'dayofweek':
		try:
			obj = DayOfWeek.objects.get(pk=pk)
		except DayOfWeek.DoesNotExist:
			return HttpResponse(status=404)
		g = dayofweek_to_rdf(obj)
	elif type == 'calendar':
		try:
			obj = Calendar.objects.get(pk=pk)
		except Calendar.DoesNotExist:
			return HttpResponse(status=404)
		g = calendar_to_rdf(obj)
		g.add((EOLAS_NS['Calendar'], rdflib.SKOS.prefLabel, rdflib.Literal("Calendar")))
	elif type == 'month':
		try:
			obj = Month.objects.get(pk=pk)
		except Month.DoesNotExist:
			return HttpResponse(status=404)
		g = month_to_rdf(obj)
	elif type == 'festival':
		try:
			obj = Festival.objects.get(pk=pk)
		except Festival.DoesNotExist:
			return HttpResponse(status=404)
		g = festival_to_rdf(obj)
		g.add((EOLAS_NS['Festival'], rdflib.SKOS.prefLabel, rdflib.Literal("Festival")))
	elif type == 'memory':
		try:
			obj = Memory.objects.get(pk=pk)
		except Memory.DoesNotExist:
			return HttpResponse(status=404)
		g = memory_to_rdf(obj)
		g.add((EOLAS_NS['Memory'], rdflib.SKOS.prefLabel, rdflib.Literal("Memory")))
	elif type == 'number':
		try:
			obj = Number.objects.get(pk=pk)
		except Number.DoesNotExist:
			return HttpResponse(status=404)
		g = number_to_rdf(obj)
		g.add((EOLAS_NS['Number'], rdflib.SKOS.prefLabel, rdflib.Literal("Number")))
	elif type == 'transportmode':
		try:
			obj = TransportMode.objects.get(pk=pk)
		except TransportMode.DoesNotExist:
			return HttpResponse(status=404)
		g = transportmode_to_rdf(obj)
	elif type == 'languagefamily':
		try:
			obj = LanguageFamily.objects.get(code=pk)
		except LanguageFamily.DoesNotExist:
			return HttpResponse(status=404)
		g = languagefamily_to_rdf(obj)
	elif type == 'language':
		try:
			obj = Language.objects.get(code=pk)
		except Language.DoesNotExist:
			return HttpResponse(status=404)
		g = language_to_rdf(obj)
	elif type == 'historicalevent':
		try:
			obj = HistoricalEvent.objects.get(pk=pk)
		except HistoricalEvent.DoesNotExist:
			return HttpResponse(status=404)
		g = historicalevent_to_rdf(obj)
		g.add((EOLAS_NS['HistoricalEvent'], rdflib.SKOS.prefLabel, rdflib.Literal("Historical Event")))
	else:
		return HttpResponse(status=404)
	return HttpResponse(g.serialize(format=format), content_type=f'{content_type}; charset={settings.DEFAULT_CHARSET}')

@api_auth
def all_rdf(request):
	# Serialize all items of every type into a single RDF graph
	format, content_type = pick_best_rdf_format(request)
	g = rdflib.Graph()
	g.bind('eolas', EOLAS_NS)
	g.bind('loc', LOC_NS)
	g += ontology_graph()
	for obj in PlaceType.objects.all():
		g += placetype_to_rdf(obj)
	for obj in Place.objects.all():
		g += place_to_rdf(obj)
	for obj in DayOfWeek.objects.all():
		g += dayofweek_to_rdf(obj)
	for obj in Calendar.objects.all():
		g += calendar_to_rdf(obj)
	for obj in Month.objects.all():
		g += month_to_rdf(obj)
	for obj in Festival.objects.all():
		g += festival_to_rdf(obj)
	for obj in Memory.objects.all():
		g += memory_to_rdf(obj)
	for obj in Number.objects.all():
		g += number_to_rdf(obj)
	for obj in TransportMode.objects.all():
		g += transportmode_to_rdf(obj)
	for obj in LanguageFamily.objects.all():
		g += languagefamily_to_rdf(obj)
	for obj in Language.objects.all():
		g += language_to_rdf(obj)
	for obj in HistoricalEvent.objects.all():
		g += historicalevent_to_rdf(obj)
	return HttpResponse(g.serialize(format=format), content_type=f'{content_type}; charset={settings.DEFAULT_CHARSET}')

def place_to_rdf(place):
	place_uri = rdflib.URIRef(place.get_absolute_url())
	type_uri = rdflib.URIRef(place.type.get_absolute_url())
	g = rdflib.Graph()
	g.bind('eolas', EOLAS_NS)
	g.add((place_uri, rdflib.RDF.type, type_uri))
	g.add((place_uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(place))))
	g.add((place_uri, EOLAS_NS.isFictional, rdflib.Literal(place.fictional)))
	g.add((place_uri, rdflib.RDFS.label, rdflib.Literal(place.name)))
	for alt in place.alternate_names:
		g.add((place_uri, rdflib.RDFS.label, rdflib.Literal(alt)))
	for container in place.located_in.all():
		container_uri = rdflib.URIRef(container.get_absolute_url())
		g.add((place_uri, rdflib.SDO.containedInPlace, container_uri))
	return g

def placetype_to_rdf(placetype):
	type_uri = rdflib.URIRef(placetype.get_absolute_url())
	g = rdflib.Graph()
	g.add((type_uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(placetype))))
	g.add((type_uri, rdflib.RDFS.subClassOf, rdflib.SDO.Place))
	return g

def dayofweek_to_rdf(day):
	day_uri = rdflib.URIRef(day.get_absolute_url())
	g = rdflib.Graph()
	g.bind('eolas', EOLAS_NS)
	g.add((day_uri, rdflib.RDF.type, rdflib.TIME.DayOfWeek))
	g.add((day_uri, rdflib.SKOS.prefLabel, rdflib.Literal(day.name)))
	g.add((day_uri, rdflib.RDFS.label, rdflib.Literal(day.name)))
	g.add((day_uri, EOLAS_NS.orderInWeek, rdflib.Literal(day.order)))
	return g

def calendar_to_rdf(calendar):
	calendar_uri = rdflib.URIRef(calendar.get_absolute_url())
	g = rdflib.Graph()
	g.bind('eolas', EOLAS_NS)
	g.add((calendar_uri, rdflib.RDF.type, EOLAS_NS.Calendar))
	g.add((calendar_uri, rdflib.SKOS.prefLabel, rdflib.Literal(calendar.name)))
	g.add((calendar_uri, rdflib.RDFS.label, rdflib.Literal(calendar.name)))
	return g

def month_to_rdf(month):
	month_uri = rdflib.URIRef(month.get_absolute_url())
	calendar_uri = rdflib.URIRef(month.calendar.get_absolute_url())
	g = rdflib.Graph()
	g.bind('eolas', EOLAS_NS)
	g.add((month_uri, rdflib.RDF.type, rdflib.TIME.MonthOfYear))
	g.add((month_uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(month))))
	g.add((month_uri, rdflib.RDFS.label, rdflib.Literal(month.name)))
	g.add((month_uri, EOLAS_NS.calendar, calendar_uri))
	g.add((month_uri, EOLAS_NS.orderInCalendar, rdflib.Literal(month.order_in_calendar)))
	return g

def festival_to_rdf(festival):
	festival_uri = rdflib.URIRef(festival.get_absolute_url())
	g = rdflib.Graph()
	g.bind('eolas', EOLAS_NS)
	g.add((festival_uri, rdflib.RDF.type, EOLAS_NS.Festival))
	g.add((festival_uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(festival))))
	g.add((festival_uri, rdflib.RDFS.label, rdflib.Literal(festival.name)))
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
	memory_uri = rdflib.URIRef(memory.get_absolute_url())
	g = rdflib.Graph()
	g.bind('eolas', EOLAS_NS)
	g.add((memory_uri, rdflib.RDF.type, EOLAS_NS.Memory))
	g.add((memory_uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(memory))))
	g.add((memory_uri, rdflib.RDFS.label, rdflib.Literal(memory.name)))
	if memory.description:
		g.add((memory_uri, rdflib.DC.description, rdflib.Literal(memory.description)))
	if memory.year is not None:
		datetime_bnode = rdflib.BNode()
		g.add((memory_uri, EOLAS_NS.occuredOn, datetime_bnode))
		g.add((datetime_bnode, rdflib.TIME.year, rdflib.Literal(memory.year)))
	return g

def number_to_rdf(number):
	number_uri = rdflib.URIRef(number.get_absolute_url())
	g = rdflib.Graph()
	g.bind('eolas', EOLAS_NS)
	g.add((number_uri, rdflib.RDF.type, EOLAS_NS.Number))
	g.add((number_uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(number))))
	g.add((number_uri, rdflib.RDFS.label, rdflib.Literal(number.name)))
	if number.value is not None:
		g.add((number_uri, EOLAS_NS.numericValue, rdflib.Literal(number.value, datatype=rdflib.XSD.decimal)))
	return g

def transportmode_to_rdf(transportmode):
	transport_uri = rdflib.URIRef(transportmode.get_absolute_url())
	g = rdflib.Graph()
	g.bind('eolas', EOLAS_NS)
	g.bind('dbpedia', DBPEDIA_NS)
	g.add((transport_uri, rdflib.RDF.type, DBPEDIA_NS.MeanOfTransportation))
	g.add((transport_uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(transportmode))))
	g.add((transport_uri, rdflib.RDFS.label, rdflib.Literal(transportmode.name)))
	return g

def languagefamily_to_rdf(languagefamily):
	languagefamily_uri = rdflib.URIRef(languagefamily.get_absolute_url())
	g = rdflib.Graph()
	g.bind('loc', LOC_NS)
	g.add((languagefamily_uri, rdflib.RDF.type, rdflib.URIRef("http://id.loc.gov/vocabulary/iso639-5/iso639-5_Language")))
	g.add((languagefamily_uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(languagefamily))))
	g.add((languagefamily_uri, rdflib.RDFS.label, rdflib.Literal(languagefamily.name)))
	if languagefamily.parent:
		g.add((languagefamily_uri, LOC_NS.hasBroaderAuthority, rdflib.URIRef(f"http://id.loc.gov/vocabulary/iso639-5/{languagefamily.parent.pk}")))
	return g

def language_to_rdf(language):
	language_uri = rdflib.URIRef(language.get_absolute_url())
	g = rdflib.Graph()
	g.bind('loc', LOC_NS)
	g.add((language_uri, rdflib.RDF.type, LOC_NS.Language))
	g.add((language_uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(language))))
	g.add((language_uri, rdflib.RDFS.label, rdflib.Literal(language.name)))
	g.add((language_uri, LOC_NS.hasBroaderExternalAuthority, rdflib.URIRef(language.family.get_absolute_url())))
	return g

def historicalevent_to_rdf(historicalevent):
	historicalevent_uri = rdflib.URIRef(historicalevent.get_absolute_url())
	g = rdflib.Graph()
	g.bind('eolas', EOLAS_NS)
	g.add((historicalevent_uri, rdflib.RDF.type, EOLAS_NS.HistoricalEvent))
	g.add((historicalevent_uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(historicalevent))))
	g.add((historicalevent_uri, rdflib.RDFS.label, rdflib.Literal(historicalevent.name)))
	if historicalevent.wikipedia_slug:
		g.add((historicalevent_uri, rdflib.OWL.sameAs, rdflib.URIRef(f"http://dbpedia.org/resource/{historicalevent.wikipedia_slug}")))
	if historicalevent.year is not None:
		datetime_bnode = rdflib.BNode()
		g.add((historicalevent_uri, EOLAS_NS.occuredOn, datetime_bnode))
		g.add((datetime_bnode, rdflib.TIME.year, rdflib.Literal(historicalevent.year)))
	return g