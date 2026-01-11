import os
from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.utils.translation import gettext_lazy as _
from django.utils import translation
from django.conf import settings
from .fields import *
import rdflib

BASE_URL = os.environ.get("APP_ORIGIN")
EOLAS_NS = rdflib.Namespace(f"{BASE_URL}ontology/")
DBPEDIA_NS = rdflib.Namespace("https://dbpedia.org/ontology/")
LOC_NS = rdflib.Namespace("http://www.loc.gov/mads/rdf/v1#")
WDT_NS = rdflib.Namespace("http://www.wikidata.org/prop/direct/")

class EolasModel(models.Model):
	name = RDFNameField()
	wikipedia_slug = WikipediaField()
	class Meta:
		abstract = True

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}/metadata/{self._meta.model_name}/{self.pk}/"

	def get_rdf(self, include_type_label):
		uri = rdflib.URIRef(self.get_absolute_url())
		g = rdflib.Graph()
		if (hasattr(self, 'rdf_type')):
			g.add((uri, rdflib.RDF.type, self.rdf_type))
			if include_type_label:
				for lang, _ in settings.LANGUAGES:
					with translation.override(lang):
						g.add((self.rdf_type, rdflib.SKOS.prefLabel, rdflib.Literal(translation.gettext(self._meta.verbose_name), lang=lang)))
				if (hasattr(self, 'category')):
					g.add((self.rdf_type, EOLAS_NS.hasCategory, EOLAS_NS[self.category]))
					for lang, _ in settings.LANGUAGES:
						with translation.override(lang):
							g.add((EOLAS_NS[self.category], rdflib.SKOS.prefLabel, rdflib.Literal(translation.gettext(self.category), lang=lang)))
		for field in self._meta.get_fields():
			if hasattr(field, 'get_rdf'):
				g += field.get_rdf(self)
		return g

class Category(models.TextChoices):
	PEOPLE = "People", _("People")
	ANTHROPOLOGICAL = "Anthropological", _("Anthropological")
	ANTHROPOGEOGRAPHICAL = "Anthropogeographical", _("Anthropogeographical")
	MUSICAL = "Musical", _("Musical")
	AQUATIC = "Aquatic", _("Aquatic")
	TERRESTRIAL = "Terrestrial", _("Terrestrial")
	COSMIC = "Cosmic", _("Cosmic")
	SUPERNATURAL = "Supernatural", _("Supernatural")
	HISTORICAL = "Historical", _("Historical")
	TEMPORAL = "Temporal", _("Temporal")
	MATHEMATICAL = "Mathematical", _("Mathematical")
	TECHNOLOGICAL = "Technological", _("Technological")
	METEOROLOGICAL = "Meteorological", _("Meteorological")
	META = "Meta", _("Meta")

class PlaceType(EolasModel):
	plural = RDFCharField(
		max_length=255,
		verbose_name=_('plural'),
		null=False,
		blank=False,
		unique=True,
	)
	category = models.CharField(
		choices=Category,
		verbose_name=_('category'),
		null=False,
		blank=False,
	)
	class Meta:
		verbose_name = _('Place Type')
		verbose_name_plural = _('Place Types')
		ordering = ["name"]

	def __str__(self):
		return self.name.title()

	def get_rdf(self, include_type_label):
		uri = rdflib.URIRef(self.get_absolute_url())
		g = super().get_rdf(include_type_label)
		g.add((uri, rdflib.RDFS.subClassOf, rdflib.SDO.Place))
		g.add((uri, EOLAS_NS.hasCategory, EOLAS_NS[self.category]))
		if include_type_label:
			for lang, _ in settings.LANGUAGES:
				with translation.override(lang):
					g.add((EOLAS_NS[self.category], rdflib.SKOS.prefLabel, rdflib.Literal(translation.gettext(self.category), lang=lang)))
		return g

class Place(EolasModel):
	rdf_type = rdflib.SDO.Place # Particular places have their own PlaceType, but all of those inherit from SDO.Place
	name = RDFNameField(unique=False)
	type = RDFForeignKey(
		PlaceType,
		on_delete=models.RESTRICT,
		null=False,
		blank=False,
	)
	alternate_names = ArrayField(
		models.CharField(max_length=255),
		blank=True,
		default=list,
		verbose_name=_('also known as'),
		help_text=_("Enter alternate names separated by commas."),
	)
	fictional = RDFBooleanField(
		default=False,
		verbose_name=_('fictional'),
		rdf_predicate=EOLAS_NS.isFictional,
		db_comment='Whether or not a place is fictional.',
	)
	located_in = RDFManyToManyField(
		'self',
		symmetrical=False,
		blank=True,
		related_name='contains',
		verbose_name=_('located in'),
		rdf_predicate=rdflib.SDO.containedInPlace,
		rdf_label="Contained In Place",
		rdf_inverse_predicate=rdflib.SDO.containsPlace,
		rdf_inverse_label="Contains Place",
	)
	metonym = models.CharField(
		blank=True,
		verbose_name=_('metonym'),
		max_length=255,
		help_text=_("Something this place is often used as a substitue for")
	)
	class Meta:
		verbose_name = _('Place')
		verbose_name_plural = _('Places')
		ordering = ["name"]
		db_table_comment = "Entities that have a somewhat fixed, physical extension."

	def __str__(self):
		# Build a queryset matching either exact name or element in alternate_names
		qs = Place.objects.filter(
			models.Q(name__iexact=self.name) |
			models.Q(alternate_names__contains=[self.name])
		)
		if qs.count() > 1:
			return f"{self.name} ({self.type})"
		return self.name

	def get_rdf(self, include_type_label):
		uri = rdflib.URIRef(self.get_absolute_url())
		g = rdflib.Graph()
		g.add((uri, rdflib.SKOS.prefLabel, rdflib.Literal(str(self))))
		for alt in self.alternate_names:
			g.add((uri, rdflib.RDFS.label, rdflib.Literal(alt)))
		type_uri = rdflib.URIRef(self.type.get_absolute_url())
		g.add((uri, rdflib.RDF.type, type_uri))
		if include_type_label:
			g += self.type.get_rdf(include_type_label)
		g += self._meta.get_field('fictional').get_rdf(self)
		g += self._meta.get_field('located_in').get_rdf(self)
		if self.metonym:
			# The metonym field is actually a label for the thing, so create a bnode for the thing itself
			metonym_bnode = rdflib.BNode()
			g.add((uri, EOLAS_NS.metonym, metonym_bnode))
			g.add((metonym_bnode, rdflib.SKOS.prefLabel, rdflib.Literal(self.metonym)))
		return g

class DayOfWeek(EolasModel):
	rdf_type = rdflib.TIME.DayOfWeek
	category = Category.TEMPORAL
	order = RDFIntegerField(
		verbose_name=_('order'),
		null=False,
		blank=False,
		unique=True,
		rdf_predicate=EOLAS_NS.orderInWeek,
		db_comment='Order of day in the week.',
	)
	class Meta:
		verbose_name = _('Day of the Week')
		verbose_name_plural = _('Days of the Week')
		ordering = ['order']

class Calendar(EolasModel):
	rdf_type = EOLAS_NS.Calendar
	category = Category.TEMPORAL
	class Meta:
		verbose_name = _('Calendar')
		verbose_name_plural = _('Calendars')
		ordering = ["name"]
		db_table_comment = "A system for organizing dates."

class Month(EolasModel):
	rdf_type = rdflib.TIME.MonthOfYear
	category = Category.TEMPORAL
	name = RDFNameField(unique=False)
	calendar = RDFForeignKey(
		Calendar,
		on_delete=models.RESTRICT,
		null=False,
		blank=False,
		rdf_predicate=EOLAS_NS.calendar,
		rdf_inverse_predicate=EOLAS_NS.containsMonth,
		rdf_inverse_label="Contains Month",
		db_comment='Calendar this month belongs to.',
	)
	order_in_calendar = RDFIntegerField(
		verbose_name=_('order in calendar'),
		null=False,
		blank=False,
		rdf_predicate=EOLAS_NS.orderInCalendar,
		db_comment='Order of month in calendar.',
	)
	class Meta:
		verbose_name = _('Month')
		verbose_name_plural = _('Months')
		ordering = ['calendar', 'order_in_calendar']
		unique_together = [['calendar', 'name'],['calendar', 'order_in_calendar']]

	def __str__(self):
		# Check if this name occurs multiple times (case-insensitive)
		qs = Month.objects.filter(name__iexact=self.name)
		if qs.count() > 1:
			return f"{self.name} ({self.calendar})"
		return self.name

class HistoricalEvent(EolasModel):
	rdf_type = EOLAS_NS.HistoricalEvent
	category = Category.HISTORICAL
	year = RDFYearField(
		verbose_name=_('year'),
		null=True,
		blank=True,
		help_text=_('Approximate year of the event, in the Gregorian Calendar'),
		rdf_predicate=EOLAS_NS.occuredOn,
		rdf_label="Occured On",
		db_comment='The approximate point in time an event occured',
	)
	class Meta:
		verbose_name = _('Historical Event')
		verbose_name_plural = _('Historical Events')
		ordering = ["year", "name"]
		db_table_comment = "A notable thing that happened in the past."

class Festival(EolasModel):
	rdf_type = EOLAS_NS.Festival
	category = Category.TEMPORAL
	day_of_month = models.IntegerField(
		verbose_name=_('day of month'),
		null=True,
		blank=True,
		db_comment='When a self starts.',
	)
	month = models.ForeignKey(
		Month,
		on_delete=models.RESTRICT,
		null=True,
		blank=True,
		db_comment='When a self starts.',
	)
	commemorates = RDFForeignKey(
		HistoricalEvent,
		on_delete=models.SET_NULL,
		null=True,
		blank=True,
		rdf_predicate=WDT_NS.P547,
		rdf_label="Commemorates",
		rdf_inverse_predicate=EOLAS_NS.commemoratedBy,
		rdf_inverse_label="Commemorated by",
		db_comment='Historical event this festival commemorates',
	)
	class Meta:
		verbose_name = _('Festival')
		verbose_name_plural = _('Festivals')
		ordering = ['name']
		db_table_comment = "A recurring celebration or event."

	def get_rdf(self, include_type_label):
		uri = rdflib.URIRef(self.get_absolute_url())
		g = super().get_rdf(include_type_label)
		# Represent startDay as a blank node
		if self.day_of_month is not None or self.month is not None:
			start_day_bnode = rdflib.BNode()
			g.add((uri, EOLAS_NS.festivalStartsOn, start_day_bnode))
			if self.day_of_month is not None:
				g.add((start_day_bnode, rdflib.TIME.day, rdflib.Literal(self.day_of_month)))
			if self.month is not None:
				month_uri = rdflib.URIRef(self.month.get_absolute_url())
				g.add((start_day_bnode, rdflib.TIME.MonthOfYear, month_uri))
		return g

class Season(EolasModel):
	rdf_type = DBPEDIA_NS.Season
	category = Category.TEMPORAL
	class Meta:
		verbose_name = _('Season')
		verbose_name_plural = _('Seasons')
		ordering = ["pk"]

class Memory(EolasModel):
	rdf_type = EOLAS_NS.Memory
	category = Category.HISTORICAL
	description = RDFTextField(
		verbose_name=_('description'),
		null=False,
		blank=True,
		rdf_predicate=rdflib.DC.description,
	)
	year = RDFYearField(
		verbose_name=_('year'),
		null=True,
		blank=True,
		help_text=_('Approximate year of the memory'),
		rdf_predicate=EOLAS_NS.occuredOn,
		rdf_label="Occured On",
		db_comment='The point in time a memory is recalling.',
	)
	class Meta:
		verbose_name = _('Memory')
		verbose_name_plural = _('Memories')
		ordering = ["year", "name"]
		db_table_comment = "A remembered event or fact."

class Number(EolasModel):
	rdf_type = EOLAS_NS.Number
	category = Category.MATHEMATICAL
	value = RDFDecimalField(
		max_digits=32,
		decimal_places=2,
		verbose_name=_('value'),
		null=True,
		blank=True,
		help_text=_('Approximate value of this number, up to 2 decimal places'),
		rdf_predicate=EOLAS_NS.numericValue,
		db_comment='The (approximate) numeric value for a number.'
	)
	class Meta:
		verbose_name = _('Number')
		verbose_name_plural = _('Numbers')
		ordering = ["value", "name"]
		db_table_comment = "A numeric concept."

class TransportMode(EolasModel):
	rdf_type = DBPEDIA_NS.MeanOfTransportation
	category = Category.TECHNOLOGICAL
	class Meta:
		verbose_name = _('Mode of Transport')
		verbose_name_plural = _('Modes of Transport')
		ordering = ["name"]

class LanguageFamily(EolasModel):
	rdf_type = rdflib.URIRef("http://id.loc.gov/vocabulary/iso639-5/iso639-5_Language")
	category = Category.ANTHROPOLOGICAL
	code = RDFCharField(
		max_length=3,
		primary_key=True,
		verbose_name=_('code'),
		help_text=_('A valid ISO 639-5 code')
	)
	parent = RDFForeignKey(
		'self',
		on_delete=models.RESTRICT,
		null=True,
		blank=True,
		rdf_predicate=LOC_NS.hasBroaderAuthority,
		rdf_label='Has Broader Authority',
		rdf_inverse_predicate=LOC_NS.hasNarrowerAuthority,
		rdf_inverse_label='Has Narrower Authority',
	)
	class Meta:
		verbose_name = _('Language Family')
		verbose_name_plural = _('Language Families')
		ordering = ["code"]

	def get_absolute_url(self):
		# 'qli' is used here for language isolates, but dosen't appear in iso639-5, nor the library of congress list, so needs a local URI
		if self.pk == "qli":
			return f"{BASE_URL}/metadata/{self._meta.model_name}/{self.pk}/"
		# For other language families, use the library of congress URI
		else:
			return f"http://id.loc.gov/vocabulary/iso639-5/{self.pk}"

class Language(EolasModel):
	rdf_type = LOC_NS.Language
	category = Category.ANTHROPOLOGICAL
	code = RDFCharField(
		max_length=15,
		primary_key=True,
		verbose_name=_('code'),
		help_text=_('A valid ISO 639 code')
	)
	family = RDFForeignKey(
		LanguageFamily,
		on_delete=models.RESTRICT,
		null=False,
		blank=False,
		rdf_predicate=LOC_NS.hasBroaderExternalAuthority,
		rdf_label='Has Broader External Authority',
		rdf_inverse_predicate=LOC_NS.hasNarrowerExternalAuthority,
		rdf_inverse_label='Has Narrower External Authority',
	)

	class Meta:
		verbose_name = _('Language')
		verbose_name_plural = _('Languages')
		ordering = ["code"]

class Weather(EolasModel):
	rdf_type = EOLAS_NS.Weather
	category = Category.METEOROLOGICAL
	class Meta:
		verbose_name = _('Weather')
		verbose_name_plural = _('Weathers')
		ordering = ["name"]
		db_table_comment = "A short term state of the atmosphere."

class EthnicGroup(EolasModel):
	rdf_type = DBPEDIA_NS.EthnicGroup
	category = Category.ANTHROPOLOGICAL
	class Meta:
		verbose_name = _('Ethnic Group')
		verbose_name_plural = _('Ethnic Groups')
		ordering = ["name"]

class Direction(EolasModel):
	rdf_type = EOLAS_NS.Direction
	category = Category.MATHEMATICAL
	class Meta:
		verbose_name = _('Direction')
		verbose_name_plural = _('Directions')
		ordering = ["name"]
		db_table_comment = "The geographic location of a self relative to others"

class Organisation(EolasModel):
	rdf_type = rdflib.ORG.Organization
	category = Category.ANTHROPOLOGICAL
	class Meta:
		verbose_name = _('Organisation')
		verbose_name_plural = _('Organisations')
		ordering = ["name"]
		db_table_comment = "A group of people with a particular shared purpose"
