from django.db import models
from django.contrib.postgres.fields import ArrayField
import rdflib
from django.utils.translation import gettext_lazy as _

class RDFCharField(models.CharField):
	rdf_type = rdflib.OWL.DatatypeProperty
	def __init__(self, *args, rdf_predicate=None, rdf_label=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.rdf_predicate = rdf_predicate
		self.rdf_label = rdf_label
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
	rdf_type = rdflib.OWL.DatatypeProperty
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
	rdf_type = rdflib.OWL.DatatypeProperty
	def __init__(self, *args, rdf_predicate=None, rdf_label=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.rdf_predicate = rdf_predicate
		self.rdf_label = rdf_label
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
	rdf_type = rdflib.OWL.DatatypeProperty
	rdf_range = rdflib.TIME.DateTimeDescription
	def __init__(self, *args, rdf_predicate=None, rdf_label=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.rdf_predicate = rdf_predicate
		self.rdf_label = rdf_label
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
	rdf_type = rdflib.OWL.DatatypeProperty
	rdf_range = rdflib.XSD.decimal
	def __init__(self, *args, rdf_predicate=None, rdf_label=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.rdf_predicate = rdf_predicate
		self.rdf_label = rdf_label
	def get_rdf(self, obj):
		g = rdflib.Graph()
		value = getattr(obj, self.name)
		if value and self.rdf_predicate:
			g.add((
				rdflib.URIRef(obj.get_absolute_url()),
				self.rdf_predicate,
				rdflib.Literal(value, datatype=self.rdf_range),
			))
		return g

class RDFIntegerField(models.IntegerField):
	rdf_type = rdflib.OWL.DatatypeProperty
	rdf_range = rdflib.XSD.short
	def __init__(self, *args, rdf_predicate=None, rdf_label=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.rdf_predicate = rdf_predicate
		self.rdf_label = rdf_label
	def get_rdf(self, obj):
		g = rdflib.Graph()
		value = getattr(obj, self.name)
		if value and self.rdf_predicate:
			g.add((
				rdflib.URIRef(obj.get_absolute_url()),
				self.rdf_predicate,
				rdflib.Literal(value, datatype=self.rdf_range),
			))
		return g

class RDFBooleanField(models.BooleanField):
	rdf_type = rdflib.OWL.DatatypeProperty
	rdf_range = rdflib.XSD.boolean
	def __init__(self, *args, rdf_predicate=None, rdf_label=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.rdf_predicate = rdf_predicate
		self.rdf_label = rdf_label
	def get_rdf(self, obj):
		g = rdflib.Graph()
		value = getattr(obj, self.name)
		if value and self.rdf_predicate:
			g.add((
				rdflib.URIRef(obj.get_absolute_url()),
				self.rdf_predicate,
				rdflib.Literal(value, datatype=self.rdf_range),
			))
		return g

class WikipediaField(models.CharField):
	def __init__(self, **kwargs):
		super().__init__(
			max_length=255,
			verbose_name=_('Wikipedia URL Slug'),
			help_text=_('The URL Slug used by the primary page regarding this item on the English Language instance of Wikipedia'),
			blank=True,
		)
	def get_rdf(self, obj):
		g = rdflib.Graph()
		value = getattr(obj, self.name)
		if value:
			g.add((
				rdflib.URIRef(obj.get_absolute_url()),
				rdflib.OWL.sameAs,
				rdflib.URIRef(f"http://dbpedia.org/resource/{value}")
			))
		return g

class RDFForeignKey(models.ForeignKey):
	rdf_type = rdflib.OWL.ObjectProperty
	def __init__(self, *args, rdf_predicate=None, rdf_label=None, rdf_inverse_predicate=None, rdf_inverse_label=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.rdf_predicate = rdf_predicate
		self.rdf_label = rdf_label
		self.rdf_inverse_predicate = rdf_inverse_predicate
		self.rdf_inverse_label = rdf_inverse_label
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
	@property
	def rdf_range(self):
		return self.remote_field.model.rdf_type

class RDFManyToManyField(models.ManyToManyField):
	rdf_type = rdflib.OWL.ObjectProperty
	def __init__(self, *args, rdf_predicate=None, rdf_label=None, rdf_inverse_predicate=None, rdf_inverse_label=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.rdf_predicate = rdf_predicate
		self.rdf_label = rdf_label
		self.rdf_inverse_predicate = rdf_inverse_predicate
		self.rdf_inverse_label = rdf_inverse_label
	def get_rdf(self, obj):
		g = rdflib.Graph()
		if self.rdf_predicate:
			for subject in getattr(obj, self.name).all():
				g.add((
					rdflib.URIRef(obj.get_absolute_url()),
					self.rdf_predicate,
					rdflib.URIRef(subject.get_absolute_url()),
				))
		return g
	@property
	def rdf_range(self):
		return self.remote_field.model.rdf_type

class RDFArrayField(ArrayField):
	def __init__(self, *args, rdf_predicate=None, rdf_label=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.rdf_predicate = rdf_predicate
		self.rdf_label = rdf_label
	def get_rdf(self, obj):
		g = rdflib.Graph()
		value = getattr(obj, self.name)
		for base_field in value:
			g.add(base_field.get_rdf(obj))
		return g