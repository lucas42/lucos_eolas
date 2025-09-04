import os
import rdflib
from django.http import HttpResponse
from ..lucosauth.decorators import api_authenticate_request
from .models import Place, PlaceType

BASE_URL = os.environ.get("BASE_URL", "https://eolas.l42.eu/")
ONTOLOGY_NS = rdflib.Namespace(f"{BASE_URL}ontology/")

def admin_api_response(request, obj, rdf_serializer=None):
	"""
	If Authorization header present, authenticate API key.
	If Accept header is RDF and rdf_serializer provided, return RDF.
	Otherwise, return None (continue to normal admin view).
	"""
	resp = api_authenticate_request(request)
	if resp is not None:
		return resp
	accept = request.headers.get('Accept', '')
	if rdf_serializer and ('text/turtle' in accept):
		g = rdf_serializer(obj)
		return HttpResponse(g.serialize(format='turtle'), content_type='text/turtle')
	return None

def place_to_rdf(place):
	place_uri = rdflib.URIRef(f"{BASE_URL}metadata/place/{place.pk}")
	type_uri = rdflib.URIRef(f"{BASE_URL}metadata/placetype/{place.type.pk}")
	g = rdflib.Graph()
	g.add((type_uri, rdflib.RDFS.subClassOf, ONTOLOGY_NS.Place))
	g.add((place_uri, rdflib.RDF.type, type_uri))
	g.add((place_uri, ONTOLOGY_NS.name, rdflib.Literal(place.name)))
	g.add((place_uri, ONTOLOGY_NS.fictional, rdflib.Literal(place.fictional)))
	for alt in place.alternate_names:
		g.add((place_uri, ONTOLOGY_NS.alternateName, rdflib.Literal(alt)))
	for container in place.located_in.all():
		container_uri = rdflib.URIRef(f"{BASE_URL}metadata/place/{container.pk}")
		g.add((place_uri, ONTOLOGY_NS.locatedIn, container_uri))
	return g

def placetype_to_rdf(placetype):
	type_uri = rdflib.URIRef(f"{BASE_URL}metadata/placetype/{placetype.pk}")
	g = rdflib.Graph()
	g.add((type_uri, rdflib.RDF.type, ONTOLOGY_NS.PlaceType))
	g.add((type_uri, ONTOLOGY_NS.name, rdflib.Literal(placetype.name)))
	g.add((type_uri, ONTOLOGY_NS.plural, rdflib.Literal(placetype.plural)))
	g.add((type_uri, rdflib.RDFS.subClassOf, ONTOLOGY_NS.Place))
	return g

def api_authenticate_request(request):
	"""
	If Authorization header is present and valid, sets request.user.
	If invalid, returns a 403 response. Otherwise returns None.
	"""
	if 'HTTP_AUTHORIZATION' in request.META:
		try:
			authmeth, auth = request.META['HTTP_AUTHORIZATION'].split(' ', 1)
		except ValueError:
			return HttpResponse(status=400)
		if authmeth.lower() == 'key':
			from ..lucosauth.envvars import getUserByKey
			user = getUserByKey(apikey=auth)
			if user:
				request.user = user
			else:
				return HttpResponse(status=403)
	return None