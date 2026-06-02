from django.db import models
from django.contrib.postgres.fields import ArrayField
from django import forms
import re
import logging
import rdflib
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)

# Characters that are not valid in a URI and would cause RDF serialisation to fail
INVALID_URI_RE = re.compile(r'[\s<>"{}|\\^`\[\]]')

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
	def __init__(self, unique=True, **kwargs):
		self._unique_override = unique
		super().__init__(
			max_length=255,
			verbose_name=_('name'),
			null=False,
			blank=False,
			unique=unique,
		)

	def deconstruct(self):
		name, path, args, kwargs = super().deconstruct()
		# Django's base Field.deconstruct() only includes `unique=True` (not False).
		# RDFNameField defaults to unique=True, so when unique=False is explicitly
		# set we must include it here — otherwise Django reconstructs the field with
		# the default unique=True, silently applying a unique constraint the model
		# author intended to suppress.
		if not self.unique:
			kwargs['unique'] = False
		return name, path, args, kwargs

	def get_rdf(self, obj, value=None):
		g = rdflib.Graph()
		uri = rdflib.URIRef(obj.get_absolute_url())
		if value is None:
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
			if INVALID_URI_RE.search(value):
				logger.warning(
					"Invalid Wikipedia slug '%s' on %s id=%s — skipping from RDF output",
					value, obj.__class__.__name__, obj.pk,
				)
				return g
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

class ArrayWidget(forms.SelectMultiple):
	"""Tag/chip input widget for ArrayFields.

	Renders as a <select multiple> so Django admin's bundled Select2 can be
	initialised in tags mode — each array item becomes a removable chip.
	Existing values are pre-populated as selected <option> elements so they
	appear as chips when the page loads.

	value_from_datadict collects the multiple POST values and joins them with
	a comma so that SimpleArrayField.to_python() can split them as usual.
	"""

	def __init__(self, *args, **kwargs):
		super().__init__(*args, **kwargs)
		self.attrs['class'] = 'array-field-input'

	def optgroups(self, name, value, attrs=None):
		"""Build one selected <option> per existing value (no fixed choices list)."""
		groups = []
		for i, v in enumerate(value or []):
			if v:
				option = self.create_option(name, v, v, True, i, attrs=attrs)
				groups.append((None, [option], i))
		return groups

	def value_from_datadict(self, data, files, name):
		"""Collect the multiple POST values and return a comma-separated string."""
		values = data.getlist(name)
		return ','.join(v.strip() for v in values if v.strip())

	class Media:
		js = (
			'admin/js/jquery.init.js',
			'admin/js/vendor/select2/select2.full.js',
			'array-field-widget.js',
		)
		css = {
			'all': ('admin/css/vendor/select2/select2.min.css',)
		}


class RDFArrayField(ArrayField):
	def __init__(self, *args, rdf_predicate=None, rdf_label=None, **kwargs):
		super().__init__(*args, **kwargs)
		self.rdf_predicate = rdf_predicate
		self.rdf_label = rdf_label
	def get_rdf(self, obj):
		g = rdflib.Graph()
		values = getattr(obj, self.name) or []
		for value in values:
			g += self.base_field.get_rdf(obj, value=value)
		return g
	def formfield(self, **kwargs):
		kwargs.setdefault('widget', ArrayWidget)
		return super().formfield(**kwargs)