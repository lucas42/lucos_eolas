## Content Negotiation utility functions

# Mapping MIME types to rdflib serialization format
RDF_FORMATS = {
	"text/turtle": "turtle",
	"application/ld+json": "json-ld",
	"application/rdf+xml": "xml",
	"application/n-triples": "nt",
	"application/xml": "xml",  # Sometimes used for RDF/XML
}
def parse_accept_header(request):
	"""
	Parses an Accept header and returns a list of (mime, qvalue) sorted by qvalue descending.
	"""
	accept = request.headers.get('Accept', '')
	parts = accept.split(",")
	mimes = []
	for part in parts:
		subparts = part.split(";")
		mime = subparts[0].strip()
		q = 1.0
		for sub in subparts[1:]:
			if sub.strip().startswith("q="):
				try:
					q = float(sub.strip()[2:])
				except ValueError:
					pass
		mimes.append((mime, q))
	mimes.sort(key=lambda tup: tup[1], reverse=True)
	return mimes

def pick_best_rdf_format(request):
	"""
	Returns the best RDF mime type and rdflib serialization format for the Accept header.
	"""
	parsed = parse_accept_header(request)
	for mime, _ in parsed:
		if mime in RDF_FORMATS.keys():
			return RDF_FORMATS.get(mime, "turtle"), mime
		elif mime == "*/*":
			# Once */* is reached in priority order, don't consider anything lower
			continue
	# If no priority mime is found, return the default (first in RDF_FORMATS)
	return next(iter(RDF_FORMATS.items()))[::-1]
	

def choose_rdf_over_html(request):
	"""
	Returns True if the client would prefer some form of RDF more than HTML.
	Otherwise returns False
	"""
	parsed = parse_accept_header(request)
	rdf_weight = 0
	html_weight = 0
	for mime, q in parsed:
		if mime in RDF_FORMATS.keys():
			if q > rdf_weight:
				rdf_weight = q
		if mime == "text/html":
			if q > html_weight:
				html_weight = q
	# Only redirect to RDF if rdf_weight is non-zero and is preferred or equal to html
	return (rdf_weight > 0 and rdf_weight >= html_weight)
