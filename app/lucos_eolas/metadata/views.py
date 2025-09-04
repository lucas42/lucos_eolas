import os
import rdflib
from django.http import HttpResponseRedirect, HttpResponse
from .models import Place, PlaceType
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
			place = Place.objects.get(pk=pk)
		except Place.DoesNotExist:
			return HttpResponse(status=404)
		g = place_to_rdf(place)
	elif type == 'placetype':
		try:
			placetype = PlaceType.objects.get(pk=pk)
		except PlaceType.DoesNotExist:
			return HttpResponse(status=404)
		g = placetype_to_rdf(placetype)
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