from django.db import models
from django.contrib.postgres.fields import ArrayField
import rdflib
from django.utils.translation import gettext_lazy as _

class RDFCharField(models.CharField):
	def __init__(self, *args, rdf_predicate=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.rdf_predicate = rdf_predicate
	def get_rdf(self, obj):
		g = rdflib.Graph()
		value = getattr(obj, self.name)
		if value and self.rdf_predicate:
			g.add((
				rdflib.URIRef(obj.get_absolute_url()),
				self.rdf_predicate,
				rdflib.Literal(value),
			))
		return g

class RDFNameField(models.CharField):
	def __init__(self, unique=False, **kwargs):
		super().__init__(
			max_length=255,
			verbose_name=_('name'),
			null=False,
			blank=False,
			unique=unique,
		)
	def get_rdf(self, obj):
		g = rdflib.Graph()
		uri = rdflib.URIRef(obj.get_absolute_url())
		value = getattr(obj, self.name)
		g.add((uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(obj))))
		g.add((uri, rdflib.RDFS.label, rdflib.Literal(value)))
		return g

class RDFTextField(models.TextField):
	def __init__(self, *args, rdf_predicate=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.rdf_predicate = rdf_predicate
	def get_rdf(self, obj):
		g = rdflib.Graph()
		value = getattr(obj, self.name)
		if value and self.rdf_predicate:
			g.add((
				rdflib.URIRef(obj.get_absolute_url()),
				self.rdf_predicate,
				rdflib.Literal(value),
			))
		return g

class RDFYearField(models.IntegerField):
	def __init__(self, *args, rdf_predicate=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.rdf_predicate = rdf_predicate
	def get_rdf(self, obj):
		g = rdflib.Graph()
		value = getattr(obj, self.name)
		if value and self.rdf_predicate:
			datetime_bnode = rdflib.BNode()
			g.add((
				rdflib.URIRef(obj.get_absolute_url()),
				self.rdf_predicate,
				datetime_bnode,
			))
			g.add((
				datetime_bnode,
				rdflib.TIME.year,
				rdflib.Literal(value)
			))
		return g

class RDFDecimalField(models.DecimalField):
	def __init__(self, *args, rdf_predicate=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.rdf_predicate = rdf_predicate
	def get_rdf(self, obj):
		g = rdflib.Graph()
		value = getattr(obj, self.name)
		if value and self.rdf_predicate:
			g.add((
				rdflib.URIRef(obj.get_absolute_url()),
				self.rdf_predicate,
				rdflib.Literal(value, datatype=rdflib.XSD.decimal),
			))
		return g

class RDFIntegerField(models.IntegerField):
	def __init__(self, *args, rdf_predicate=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.rdf_predicate = rdf_predicate
	def get_rdf(self, obj):
		g = rdflib.Graph()
		value = getattr(obj, self.name)
		if value and self.rdf_predicate:
			g.add((
				rdflib.URIRef(obj.get_absolute_url()),
				self.rdf_predicate,
				rdflib.Literal(value, datatype=rdflib.XSD.short),
			))
		return g

class WikipediaField(models.CharField):
	def get_rdf(self, obj):
		g = rdflib.Graph()
		value = getattr(obj, self.name)
		g.add((
			rdflib.URIRef(obj.get_absolute_url()),
			rdflib.OWL.sameAs,
			rdflib.URIRef(f"http://dbpedia.org/resource/{value}")
		))
		return g

class RDFForeignKey(models.ForeignKey):
	def __init__(self, *args, rdf_predicate=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.rdf_predicate = rdf_predicate
	def get_rdf(self, obj):
		g = rdflib.Graph()
		value = getattr(obj, self.name)
		if value and self.rdf_predicate:
			g.add((
				rdflib.URIRef(obj.get_absolute_url()),
				self.rdf_predicate,
				rdflib.URIRef(value.get_absolute_url()),
			))
		return g

class RDFArrayField(ArrayField):
	def __init__(self, *args, rdf_predicate=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.rdf_predicate = rdf_predicate
	def get_rdf(self, obj):
		g = rdflib.Graph()
		value = getattr(obj, self.name)
		for base_field in value:
			g.add(base_field.get_rdf(obj))
		return g