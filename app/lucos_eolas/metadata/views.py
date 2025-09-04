import os
import rdflib
from django.http import HttpResponseRedirect, HttpResponse, JsonResponse
from .models import Place, PlaceType, DayOfWeek, Calendar, Month, Festival, Memory, Number, TransportMode
from ..lucosauth.decorators import api_auth

BASE_URL = os.environ.get("BASE_URL")
ONTOLOGY_NS = rdflib.Namespace(f"{BASE_URL}ontology/")

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

def thing_entrypoint(request, type, pk):
	accept = request.headers.get('Accept', '')
	if 'text/turtle' in accept or 'application/rdf+xml' in accept or 'application/ld+json' in accept:
		# 303 See Other to the data endpoint for RDF requests
		return HttpResponseRedirect(f'/metadata/{type}/{pk}/data/')
	else:
		# 303 See Other to the admin change endpoint for non-RDF requests
		return HttpResponseRedirect(f'/metadata/{type}/{pk}/change/')

@api_auth
def thing_data(request, type, pk):
	# API key auth handled by decorator
	accept = request.headers.get('Accept', '')
	if type == 'place':
		try:
			obj = Place.objects.get(pk=pk)
		except Place.DoesNotExist:
			return HttpResponse(status=404)
		g = place_to_rdf(obj)
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
	elif type == 'memory':
		try:
			obj = Memory.objects.get(pk=pk)
		except Memory.DoesNotExist:
			return HttpResponse(status=404)
		g = memory_to_rdf(obj)
	elif type == 'number':
		try:
			obj = Number.objects.get(pk=pk)
		except Number.DoesNotExist:
			return HttpResponse(status=404)
		g = number_to_rdf(obj)
	elif type == 'transportmode':
		try:
			obj = TransportMode.objects.get(pk=pk)
		except TransportMode.DoesNotExist:
			return HttpResponse(status=404)
		g = transportmode_to_rdf(obj)
	else:
		return HttpResponse(status=404)
	# Default to Turtle serialization for now
	return HttpResponse(g.serialize(format='turtle'), content_type='text/turtle')

def place_to_rdf(place):
	place_uri = rdflib.URIRef(f"{BASE_URL}metadata/place/{place.pk}/")
	type_uri = rdflib.URIRef(f"{BASE_URL}metadata/placetype/{place.type.pk}/")
	g = rdflib.Graph()
	g.add((place_uri, rdflib.RDF.type, type_uri))
	g.add((place_uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(place))))
	g.add((place_uri, ONTOLOGY_NS.fictional, rdflib.Literal(place.fictional)))
	g.add((place_uri, rdflib.RDFS.label, rdflib.Literal(place.name)))
	for alt in place.alternate_names:
		g.add((place_uri, rdflib.RDFS.label, rdflib.Literal(alt)))
	for container in place.located_in.all():
		container_uri = rdflib.URIRef(f"{BASE_URL}metadata/place/{container.pk}/")
		g.add((place_uri, ONTOLOGY_NS.locatedIn, container_uri))
	return g

def placetype_to_rdf(placetype):
	type_uri = rdflib.URIRef(f"{BASE_URL}metadata/placetype/{placetype.pk}/")
	g = rdflib.Graph()
	g.add((type_uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(placetype))))
	g.add((type_uri, rdflib.RDFS.subClassOf, ONTOLOGY_NS.Place))
	return g

def dayofweek_to_rdf(day):
	day_uri = rdflib.URIRef(f"{BASE_URL}metadata/dayofweek/{day.pk}/")
	g = rdflib.Graph()
	g.add((day_uri, rdflib.RDF.type, ONTOLOGY_NS.DayOfWeek))
	g.add((day_uri, rdflib.SKOS.prefLabel, rdflib.Literal(day.name)))
	g.add((day_uri, rdflib.RDFS.label, rdflib.Literal(day.name)))
	g.add((day_uri, ONTOLOGY_NS.order, rdflib.Literal(day.order)))
	return g

def calendar_to_rdf(calendar):
	calendar_uri = rdflib.URIRef(f"{BASE_URL}metadata/calendar/{calendar.pk}/")
	g = rdflib.Graph()
	g.add((calendar_uri, rdflib.RDF.type, ONTOLOGY_NS.Calendar))
	g.add((calendar_uri, rdflib.SKOS.prefLabel, rdflib.Literal(calendar.name)))
	g.add((calendar_uri, rdflib.RDFS.label, rdflib.Literal(calendar.name)))
	return g

def month_to_rdf(month):
	month_uri = rdflib.URIRef(f"{BASE_URL}metadata/month/{month.pk}/")
	calendar_uri = rdflib.URIRef(f"{BASE_URL}metadata/calendar/{month.calendar.pk}/")
	g = rdflib.Graph()
	g.add((month_uri, rdflib.RDF.type, ONTOLOGY_NS.Month))
	g.add((month_uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(month))))
	g.add((month_uri, rdflib.RDFS.label, rdflib.Literal(month.name)))
	g.add((month_uri, ONTOLOGY_NS.calendar, calendar_uri))
	g.add((month_uri, ONTOLOGY_NS.orderInCalendar, rdflib.Literal(month.order_in_calendar)))
	return g

def festival_to_rdf(festival):
	festival_uri = rdflib.URIRef(f"{BASE_URL}metadata/festival/{festival.pk}/")
	g = rdflib.Graph()
	g.add((festival_uri, rdflib.RDF.type, ONTOLOGY_NS.Festival))
	g.add((festival_uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(festival))))
	g.add((festival_uri, rdflib.RDFS.label, rdflib.Literal(festival.name)))
	if festival.day_of_month is not None:
		g.add((festival_uri, ONTOLOGY_NS.dayOfMonth, rdflib.Literal(festival.day_of_month)))
	if festival.month is not None:
		month_uri = rdflib.URIRef(f"{BASE_URL}metadata/month/{festival.month.pk}/")
		g.add((festival_uri, ONTOLOGY_NS.month, month_uri))
	return g

def memory_to_rdf(memory):
	memory_uri = rdflib.URIRef(f"{BASE_URL}metadata/memory/{memory.pk}/")
	g = rdflib.Graph()
	g.add((memory_uri, rdflib.RDF.type, ONTOLOGY_NS.Memory))
	g.add((memory_uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(memory))))
	g.add((memory_uri, rdflib.RDFS.label, rdflib.Literal(memory.name)))
	if memory.description:
		g.add((memory_uri, ONTOLOGY_NS.description, rdflib.Literal(memory.description)))
	if memory.year is not None:
		g.add((memory_uri, ONTOLOGY_NS.year, rdflib.Literal(memory.year)))
	return g

def number_to_rdf(number):
	number_uri = rdflib.URIRef(f"{BASE_URL}metadata/number/{number.pk}/")
	g = rdflib.Graph()
	g.add((number_uri, rdflib.RDF.type, ONTOLOGY_NS.Number))
	g.add((number_uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(number))))
	g.add((number_uri, rdflib.RDFS.label, rdflib.Literal(number.name)))
	if number.value is not None:
		g.add((number_uri, ONTOLOGY_NS.value, rdflib.Literal(number.value)))
	return g

def transportmode_to_rdf(transportmode):
	transport_uri = rdflib.URIRef(f"{BASE_URL}metadata/transportmode/{transportmode.pk}/")
	g = rdflib.Graph()
	g.add((transport_uri, rdflib.RDF.type, ONTOLOGY_NS.TransportMode))
	g.add((transport_uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(transportmode))))
	g.add((transport_uri, rdflib.RDFS.label, rdflib.Literal(transportmode.name)))
	return g