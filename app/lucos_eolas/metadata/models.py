import os
from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.utils.translation import gettext_lazy as _
from .fields import *
import rdflib

BASE_URL = os.environ.get("BASE_URL")
EOLAS_NS = rdflib.Namespace(f"{BASE_URL}ontology/")
DBPEDIA_NS = rdflib.Namespace("https://dbpedia.org/ontology/")
LOC_NS = rdflib.Namespace("http://www.loc.gov/mads/rdf/v1#")

class PlaceType(models.Model):
	name = RDFNameField()
	plural = RDFCharField(
		max_length=255,
		verbose_name=_('plural'),
		null=False,
		blank=False,
		unique=True,
	)
	class Meta:
		verbose_name = _('Place Type')
		verbose_name_plural = _('Place Types')
		ordering = ["name"]

	def __str__(self):
		return self.name.title()

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/placetype/{self.pk}/"

class Place(models.Model):
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
	located_in = models.ManyToManyField(
		'self',
		symmetrical=False,
		blank=True,
		related_name='contains',
		verbose_name=_('located in'),
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

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/place/{self.pk}/"

class DayOfWeek(models.Model):
	rdf_type = rdflib.TIME.DayOfWeek
	name = RDFNameField()
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

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/dayofweek/{self.pk}/"

class Calendar(models.Model):
	rdf_type = EOLAS_NS.Calendar
	name = RDFNameField()
	class Meta:
		verbose_name = _('Calendar')
		verbose_name_plural = _('Calendars')
		ordering = ["name"]
		db_table_comment = "A system for organizing dates."

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/calendar/{self.pk}/"

class Month(models.Model):
	rdf_type = rdflib.TIME.MonthOfYear
	name = RDFNameField(unique=False)
	calendar = RDFForeignKey(
		Calendar,
		on_delete=models.RESTRICT,
		null=False,
		blank=False,
		rdf_predicate=EOLAS_NS.calendar,
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

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/month/{self.pk}/"

class Festival(models.Model):
	rdf_type = EOLAS_NS.Festival
	name = RDFNameField()
	day_of_month = models.IntegerField(
		verbose_name=_('day of month'),
		null=True,
		blank=True,
		db_comment='When a festival starts.',
	)
	month = models.ForeignKey(
		Month,
		on_delete=models.RESTRICT,
		null=True,
		blank=True,
		db_comment='When a festival starts.',
	)
	class Meta:
		verbose_name = _('Festival')
		verbose_name_plural = _('Festivals')
		ordering = ['name']
		db_table_comment = "A recurring celebration or event."

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/festival/{self.pk}/"

class Season(models.Model):
	rdf_type = DBPEDIA_NS.Season
	name = RDFNameField()
	class Meta:
		verbose_name = _('Season')
		verbose_name_plural = _('Seasons')
		ordering = ["pk"]

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/season/{self.pk}/"

class Memory(models.Model):
	rdf_type = EOLAS_NS.Memory
	name = RDFNameField()
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

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/memory/{self.pk}/"

class Number(models.Model):
	rdf_type = EOLAS_NS.Number
	name = RDFNameField()
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

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/number/{self.pk}/"

class TransportMode(models.Model):
	rdf_type = DBPEDIA_NS.MeanOfTransportation
	name = RDFNameField()
	class Meta:
		verbose_name = _('Mode of Transport')
		verbose_name_plural = _('Modes of Transport')
		ordering = ["name"]

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/transportmode/{self.pk}/"

class LanguageFamily(models.Model):
	rdf_type = rdflib.URIRef("http://id.loc.gov/vocabulary/iso639-5/iso639-5_Language")
	code = RDFCharField(
		max_length=3,
		primary_key=True,
		verbose_name=_('code'),
		help_text=_('A valid ISO 639-5 code')
	)
	name = RDFNameField()
	parent = RDFForeignKey(
		'self',
		on_delete=models.RESTRICT,
		null=True,
		blank=True,
		rdf_predicate=LOC_NS.hasBroaderAuthority,
		rdf_label='Has Broader Authority',
	)
	class Meta:
		verbose_name = _('Language Family')
		verbose_name_plural = _('Language Families')
		ordering = ["code"]

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		# 'qli' is used here for language isolates, but dosen't appear in iso639-5, nor the library of congress list, so needs a local URI
		if self.pk == "qli":
			return f"{BASE_URL}metadata/languagefamily/{self.pk}/"
		# For other language families, use the library of congress URI
		else:
			return f"http://id.loc.gov/vocabulary/iso639-5/{self.pk}"

class Language(models.Model):
	rdf_type = LOC_NS.Language
	code = RDFCharField(
		max_length=15,
		primary_key=True,
		verbose_name=_('code'),
		help_text=_('A valid ISO 639 code')
	)
	name = RDFNameField()
	family = RDFForeignKey(
		LanguageFamily,
		on_delete=models.RESTRICT,
		null=False,
		blank=False,
		rdf_predicate=LOC_NS.hasBroaderExternalAuthority,
		rdf_label='Has Broader External Authority',
	)

	class Meta:
		verbose_name = _('Language')
		verbose_name_plural = _('Languages')
		ordering = ["code"]

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/language/{self.pk}/"

class HistoricalEvent(models.Model):
	rdf_type = EOLAS_NS.HistoricalEvent
	name = RDFNameField()
	wikipedia_slug = WikipediaField(
		max_length=255,
		verbose_name=_('Wikipedia URL Slug'),
		help_text=_('The URL Slug used by the primary page regarding this event on the English Language instance of Wikipedia'),
		unique=True,
	)
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

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/historicalevent/{self.pk}/"

class Weather(models.Model):
	rdf_type = EOLAS_NS.Weather
	name = RDFNameField()
	class Meta:
		verbose_name = _('Weather')
		verbose_name_plural = _('Weathers')
		ordering = ["name"]
		db_table_comment = "A short term state of the atmosphere."

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/weather/{self.pk}/"

class EthnicGroup(models.Model):
	rdf_type = DBPEDIA_NS.EthnicGroup
	name = RDFNameField()
	class Meta:
		verbose_name = _('Ethnic Group')
		verbose_name_plural = _('Ethnic Groups')
		ordering = ["name"]

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/ethnicgroup/{self.pk}/"