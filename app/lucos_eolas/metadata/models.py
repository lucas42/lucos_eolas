import os
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.enums import ChoicesType
from django.utils.translation import gettext_lazy as _
from django.utils import translation
from django.conf import settings
from .fields import *
import rdflib


class CategoryChoicesType(ChoicesType):
	"""Metaclass extending ChoicesType to support per-member colour attributes.

	Members are defined as 5-tuples:
	    NAME = value, background, border, text, label
	The colour values (background, border, text) are extracted here and attached
	as instance attributes on each enum member.  The remaining (value, label)
	2-tuple is handed to the standard ChoicesType / StrEnum machinery unchanged.
	"""

	def __new__(metacls, classname, bases, classdict, **kwds):
		colour_data = {}
		for key in classdict._member_names:
			value = classdict[key]
			# Detect our extended 5-tuple: (str_value, background, border, text, label)
			if isinstance(value, tuple) and len(value) == 5:
				str_val, background, border, text, label = value
				colour_data[key] = (background, border, text)
				# Rewrite to a standard 2-tuple so ChoicesType and StrEnum handle it
				dict.__setitem__(classdict, key, (str_val, label))
		cls = super().__new__(metacls, classname, bases, classdict, **kwds)
		for name, (background, border, text) in colour_data.items():
			member = cls._member_map_[name]
			member.background = background
			member.border = border
			member.text = text
		return cls

BASE_URL = os.environ.get("APP_ORIGIN")
EOLAS_NS = rdflib.Namespace(f"{BASE_URL}/ontology/")
DBPEDIA_NS = rdflib.Namespace("https://dbpedia.org/ontology/")
LOC_NS = rdflib.Namespace("http://www.loc.gov/mads/rdf/v1#")
WDT_NS = rdflib.Namespace("http://www.wikidata.org/prop/direct/")

class EolasModel(models.Model):
	name = RDFNameField()
	alternate_names = RDFArrayField(
		RDFNameField(max_length=255),
		blank=True,
		default=list,
		verbose_name=_('also known as'),
		help_text=_("Enter alternate names separated by commas."),
	)
	wikipedia_slug = WikipediaField()
	class Meta:
		abstract = True

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}/metadata/{self._meta.model_name}/{self.pk}/"

	def get_webhook_url(self):
		"""Return the URL to include in loganne webhook events.

		Defaults to get_absolute_url(). Override on models whose canonical
		identifier is an external URI (e.g. Library of Congress) so that
		arachne receives an eolas-hosted URL it can actually fetch.
		"""
		return self.get_absolute_url()

	def to_json(self):
		"""Serialise this item to a JSON-ready dict.

		Always includes 'id', 'uri', and 'name'.  All other concrete fields on the
		model are included: ForeignKey fields are expanded to {id, uri, name} dicts;
		scalars and arrays are returned as their Python values.  Only the primary key
		and 'name' are omitted from the field loop — they are already captured under
		canonical keys in the base dict.
		"""
		data = {
			'id': self.pk,
			'uri': self.get_absolute_url(),
			'name': self.name,
		}
		for field in self._meta.local_fields:
			if field.primary_key or field.name == 'name':
				continue
			if isinstance(field, models.ForeignKey):
				related = getattr(self, field.name)
				data[field.name] = {
					'id': related.pk,
					'uri': related.get_absolute_url(),
					'name': str(related),
				} if related is not None else None
			else:
				data[field.name] = getattr(self, field.name)
		return data

	def get_rdf(self, include_type_label):
		uri = rdflib.URIRef(self.get_absolute_url())
		g = rdflib.Graph()
		if (hasattr(self, 'type')):
			type_uri = rdflib.URIRef(self.type.get_absolute_url())
			g.add((uri, rdflib.RDF.type, type_uri))
			if include_type_label:
				g += self.type.get_rdf(include_type_label)
		elif (hasattr(self, 'rdf_type')):
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

class Category(models.TextChoices, metaclass=CategoryChoicesType):
	"""Enum of eolas categories.

	Each member carries all 5 pieces of info in one place:
	    NAME = value, background, border, text, label

	The label (last element) is a lazy-translated string.  The three colour
	values are always explicit — no consumer-side defaults.  CategoryChoicesType
	extracts the colours before handing the standard 2-tuple (value, label) to
	Django / StrEnum, then sets .background, .border, .text on each member.
	"""

	#                        value                   background   border     text       label
	PEOPLE =               ("People",              "#044E00", "#033100", "#ffffff", _("People"))
	ANTHROPOLOGICAL =      ("Anthropological",     "#8affe7", "#068900", "#000000", _("Anthropological"))
	ANTHROPOGEOGRAPHICAL = ("Anthropogeographical","#aed0db", "#3f6674", "#0c1a1b", _("Anthropogeographical"))
	MUSICAL =              ("Musical",             "#000060", "#000020", "#ffffff", _("Musical"))
	AQUATIC =              ("Aquatic",             "#0085fe", "#0036b1", "#ffffff", _("Aquatic"))
	TERRESTRIAL =          ("Terrestrial",         "#652c17", "#321200", "#ffffff", _("Terrestrial"))
	COSMIC =               ("Cosmic",              "#15163a", "#000000", "#feffe8", _("Cosmic"))
	SUPERNATURAL =         ("Supernatural",        "#f1ff5f", "#674800", "#352005", _("Supernatural"))
	HISTORICAL =           ("Historical",          "#740909", "#470202", "#ffffff", _("Historical"))
	TEMPORAL =             ("Temporal",            "#fffc33", "#7f7e00", "#0f0f00", _("Temporal"))
	MATHEMATICAL =         ("Mathematical",        "#f53b0e", "#7e3d2e", "#ffffff", _("Mathematical"))
	TECHNOLOGICAL =        ("Technological",       "#c70f7a", "#8f125b", "#ffffff", _("Technological"))
	METEOROLOGICAL =       ("Meteorological",      "#ffffff", "#333333", "#000000", _("Meteorological"))
	META =                 ("Meta",               "#4a5568", "#2d3748", "#ffffff", _("Meta"))
	DRAMATURGICAL =        ("Dramaturgical",       "#5f0086", "#59007d", "#ffffff", _("Dramaturgical"))
	LITERARY =             ("Literary",            "#a22400", "#5e1500", "#ffffff", _("Literary"))

class PlaceType(EolasModel):
	rdf_type = EOLAS_NS.PlaceType
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
	fictional = RDFBooleanField(
		default=False,
		verbose_name=_('fictional'),
		rdf_predicate=EOLAS_NS.isFictional,
		db_comment='Whether or not a place is fictional.',
	)
	contained_in = RDFManyToManyField(
		'self',
		symmetrical=False,
		blank=True,
		related_name='contains',
		verbose_name=_('contained in'),
		rdf_predicate=EOLAS_NS.containedIn,
		rdf_label="Contained In Place",
		rdf_inverse_predicate=EOLAS_NS.contains,
		rdf_inverse_label="Contains Place",
	)
	partially_contained_in = RDFManyToManyField(
		'self',
		symmetrical=False,
		blank=True,
		related_name='partially_contains',
		verbose_name=_('partially contained in'),
		rdf_predicate=EOLAS_NS.partiallyContainedIn,
		rdf_label="Partially Contained In",
		rdf_inverse_predicate=EOLAS_NS.partiallyContains,
		rdf_inverse_label="Partially Contains",
	)
	territory_of = RDFManyToManyField(
		'self',
		symmetrical=False,
		blank=True,
		related_name='has_territory',
		verbose_name=_('territory of'),
		rdf_predicate=EOLAS_NS.territoryOf,
		rdf_label="Territory Of",
		rdf_inverse_predicate=EOLAS_NS.hasTerritory,
		rdf_inverse_label="Has Territory",
	)
	bounds = RDFManyToManyField(
		'self',
		symmetrical=False,
		blank=True,
		related_name='bounded_by',
		verbose_name=_('bounds'),
		rdf_predicate=EOLAS_NS.bounds,
		rdf_label="Bounds",
		rdf_inverse_predicate=EOLAS_NS.boundedBy,
		rdf_inverse_label="Bounded By",
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
		g = super().get_rdf(include_type_label)
		if self.metonym:
			# The metonym field is actually a label for the thing, so create a bnode for the thing itself
			metonym_bnode = rdflib.BNode()
			g.add((uri, EOLAS_NS.metonym, metonym_bnode))
			g.add((metonym_bnode, rdflib.SKOS.prefLabel, rdflib.Literal(self.metonym)))
		return g

	@classmethod
	def get_ontology_rdf(cls):
		g = rdflib.Graph()
		g.add((EOLAS_NS.containedIn, rdflib.RDFS.subPropertyOf, rdflib.SDO.containedInPlace))
		g.add((EOLAS_NS.contains, rdflib.RDFS.subPropertyOf, rdflib.SDO.containsPlace))
		g.add((EOLAS_NS.containedIn, rdflib.RDF.type, rdflib.OWL.TransitiveProperty))
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
	temporal_id = RDFCharField(
		max_length=20,
		null=True,
		blank=True,
		verbose_name=_('Temporal calendar ID'),
		help_text=_('The calendar identifier used by the TC39 Temporal API (e.g. "gregory", "hebrew", "islamic", "chinese", "indian").'),
		db_comment='TC39 Temporal calendar identifier for this calendar system.',
	)
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
	temporal_month_code = RDFCharField(
		max_length=4,
		null=True,
		blank=True,
		verbose_name=_('Temporal month code'),
		help_text=_('The stable month code used by the TC39 Temporal API (e.g. "M01", "M07", "M06L" for Adar II). Stable across leap/non-leap years.'),
		db_comment='TC39 Temporal monthCode for this month (stable across leap years).',
	)
	class Meta:
		verbose_name = _('Month')
		verbose_name_plural = _('Months')
		ordering = ['calendar', 'order_in_calendar']
		unique_together = [['calendar', 'name'],['calendar', 'order_in_calendar']]

	def to_json(self):
		data = super().to_json()
		# For months where temporal_month_code is not explicitly stored (non-Hebrew calendars),
		# derive it from order_in_calendar using the standard M01–M12 format.
		if not data.get('temporal_month_code'):
			data['temporal_month_code'] = f'M{self.order_in_calendar:02d}'
		return data

	def __str__(self):
		# Check if this name occurs multiple times (case-insensitive)
		qs = Month.objects.filter(name__iexact=self.name)
		if qs.count() > 1:
			return f"{self.name} ({self.calendar})"
		return self.name

class HistoricalEvent(EolasModel):
	rdf_type = EOLAS_NS.HistoricalEvent
	category = Category.HISTORICAL
	start_year = RDFYearField(
		verbose_name=_('start year'),
		null=True,
		blank=True,
		help_text=_('Approximate year the event started, in the Gregorian Calendar'),
		rdf_predicate=EOLAS_NS.startYear,
		rdf_label="Occured On",
		db_comment='The approximate point in time an event began',
	)
	end_year = RDFYearField(
		verbose_name=_('end year'),
		null=True,
		blank=True,
		help_text=_('Approximate year the event ended, in the Gregorian Calendar'),
		rdf_predicate=EOLAS_NS.endYear,
		rdf_label="Occured On",
		db_comment='The approximate point in time an event finished',
	)
	class Meta:
		verbose_name = _('Historical Event')
		verbose_name_plural = _('Historical Events')
		ordering = ["start_year", "name"]
		db_table_comment = "A notable thing that happened in the past."

class Festival(EolasModel):
	"""A recurring celebration or event.

	Temporal modelling: ``day_of_month``/``month`` capture the festival's
	**defining day** — the specific calendar date the festival is "about" (e.g.
	25 December for Christmas, 31 October for Hallowe'en).  Additional thematic
	windows around that day — multi-day observances, build-up periods, themed
	music seasons, etc. — are modelled as separate :class:`FestivalPeriod`
	records linked back to the festival.

	The two are **additive, not alternatives**:

	* A festival may have ``day_of_month``/``month`` set, one or more
	  ``FestivalPeriod`` records, both, or neither (e.g. movable feasts that
	  follow a lunar/solar rule and are computed elsewhere).
	* ``FestivalPeriod`` is **not** a replacement for ``day_of_month``.  A
	  festival with only ``day_of_month`` is fully specified — no period record
	  is required.
	* Do **not** create a ``FestivalPeriod`` that merely duplicates the
	  defining day (e.g. a 1-day "Christmas Day" period when ``day_of_month=25``
	  already captures that — it adds noise and breaks the semantic split).

	``day_of_month``/``month`` is permanent, not transitional.  See issue #226.
	"""
	rdf_type = EOLAS_NS.Festival
	category = Category.TEMPORAL
	day_of_month = models.IntegerField(
		verbose_name=_('day of month'),
		null=True,
		blank=True,
		help_text=_("The day of the month on which the festival's defining day falls."),
		db_comment='Day of the month of the festival\'s defining day.',
	)
	month = models.ForeignKey(
		Month,
		on_delete=models.RESTRICT,
		null=True,
		blank=True,
		verbose_name=_('month'),
		help_text=_("The month in which the festival's defining day falls."),
		db_comment='Month of the festival\'s defining day.',
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

class FestivalPeriod(EolasModel):
	"""An additional temporal window associated with a :class:`Festival`.

	A ``FestivalPeriod`` models a thematic window *around* a festival —
	multi-day observances, build-up periods, themed music seasons, cross-month
	stretches, etc.  It is **additive** to the festival's defining day
	(``Festival.day_of_month``/``Festival.month``), not a replacement for it.
	See the docstring on :class:`Festival` for the full semantic split.

	**Do not** create a ``FestivalPeriod`` whose only purpose is to repeat the
	defining day (e.g. a 1-day period for Christmas Day when ``day_of_month=25``
	already captures it).  A period record should always say something *more*
	than the defining day — a longer span, a thematic shift, a build-up.

	A period's shape is given by ``start_day`` + ``start_month`` + ``duration_days``.
	Three combinations are valid; the fourth is rejected by :meth:`clean`:

	+--------------+----------------+------------------------------------------+
	| ``start_day``| ``duration_days``| meaning                                |
	+==============+================+==========================================+
	| null         | null           | the whole of ``start_month``             |
	|              |                | (e.g. "themed music throughout December")|
	+--------------+----------------+------------------------------------------+
	| set          | null           | a single day: ``start_day`` of           |
	|              |                | ``start_month``                          |
	+--------------+----------------+------------------------------------------+
	| set          | set            | a span of that length starting on        |
	|              |                | ``start_day``; may cross into the        |
	|              |                | following month                          |
	+--------------+----------------+------------------------------------------+
	| null         | set            | **invalid** — a duration without a start |
	|              |                | day has no anchored meaning              |
	+--------------+----------------+------------------------------------------+

	See issue #226 for the rationale.
	"""
	rdf_type = EOLAS_NS.FestivalPeriod
	category = Category.TEMPORAL
	name = RDFNameField(unique=False)
	festival = RDFForeignKey(
		Festival,
		on_delete=models.CASCADE,
		null=False,
		blank=False,
		rdf_predicate=EOLAS_NS.periodOf,
		rdf_label="Period of",
		rdf_inverse_predicate=EOLAS_NS.hasPeriod,
		rdf_inverse_label="Has Period",
		db_comment="Festival this period belongs to.",
	)
	start_day = RDFIntegerField(
		null=True,
		blank=True,
		verbose_name=_('start day'),
		help_text=_('Day of the month on which this period begins. Leave blank for a whole-month period.'),
		rdf_predicate=EOLAS_NS.periodStartDay,
		rdf_label="Start day",
		db_comment="Day of month this period starts.",
	)
	start_month = RDFForeignKey(
		Month,
		on_delete=models.RESTRICT,
		null=True,
		blank=True,
		related_name='festival_periods',
		verbose_name=_('start month'),
		help_text=_('The month in which this period begins.'),
		rdf_predicate=EOLAS_NS.periodStartMonth,
		rdf_label="Start month",
		db_comment="Month this period starts in.",
	)
	duration_days = RDFIntegerField(
		null=True,
		blank=True,
		verbose_name=_('duration (days)'),
		help_text=_('Length of this period in days. Leave blank for a single day or a whole month.'),
		rdf_predicate=EOLAS_NS.periodDurationDays,
		rdf_label="Duration (days)",
		db_comment="Number of days this period lasts. Null means one day (if start_day set) or the entire start_month (if start_day null).",
	)
	class Meta:
		verbose_name = _('Festival Period')
		verbose_name_plural = _('Festival Periods')
		ordering = ['festival', 'start_month', 'start_day']
		db_table_comment = "A temporal period associated with a festival."

	def clean(self):
		super().clean()
		# A duration without a start day has no anchored meaning -- see the
		# table in this class's docstring.
		if self.start_day is None and self.duration_days is not None:
			raise ValidationError({
				'duration_days': _(
					'Cannot set a duration without a start day. '
					'Leave duration blank for a whole-month period, '
					'or set a start day.'
				),
			})

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
	rdf_type = EOLAS_NS.TransportMode
	category = Category.TECHNOLOGICAL
	plural = RDFCharField(
		max_length=255,
		verbose_name=_('plural'),
		null=False,
		blank=False,
		unique=True,
	)
	class Meta:
		verbose_name = _('Mode of Transport')
		verbose_name_plural = _('Modes of Transport')
		ordering = ["name"]

	def __str__(self):
		return self.name.title()

	def get_rdf(self, include_type_label):
		uri = rdflib.URIRef(self.get_absolute_url())
		g = super().get_rdf(include_type_label)
		g.add((uri, rdflib.RDFS.subClassOf, DBPEDIA_NS.MeanOfTransportation))
		g.add((uri, EOLAS_NS.hasCategory, EOLAS_NS[self.category]))
		if include_type_label:
			for lang, _ in settings.LANGUAGES:
				with translation.override(lang):
					g.add((EOLAS_NS[self.category], rdflib.SKOS.prefLabel, rdflib.Literal(translation.gettext(self.category), lang=lang)))
		return g


class Vehicle(EolasModel):
	name = RDFNameField(unique=False)
	type = RDFForeignKey(
		TransportMode,
		on_delete=models.RESTRICT,
		null=False,
		blank=False,
	)
	fictional = RDFBooleanField(
		default=False,
		verbose_name=_('fictional'),
		rdf_predicate=EOLAS_NS.isFictional,
		db_comment='Whether or not a vehicle is fictional.',
	)
	class Meta:
		verbose_name = _('Vehicle')
		verbose_name_plural = _('Vehicles')
		ordering = ["name"]

	def __str__(self):
		qs = Vehicle.objects.filter(
			models.Q(name__iexact=self.name) |
			models.Q(alternate_names__contains=[self.name])
		)
		if qs.count() > 1:
			return f"{self.name} ({self.type})"
		return self.name

class LanguageFamily(EolasModel):
	rdf_type = EOLAS_NS.LanguageFamily
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
	)
	class Meta:
		verbose_name = _('Language Family')
		verbose_name_plural = _('Language Families')
		ordering = ["name"]

	def get_rdf(self, include_type_label):
		uri = rdflib.URIRef(self.get_absolute_url())
		g = super().get_rdf(include_type_label)
		if self.parent:
			parent_uri = rdflib.URIRef(self.parent.get_absolute_url())
		else:
			parent_uri = LOC_NS.Language
		g.add((uri, rdflib.RDFS.subClassOf, parent_uri))
		g.add((uri, EOLAS_NS.hasCategory, EOLAS_NS[self.category]))
		if include_type_label:
			for lang, _ in settings.LANGUAGES:
				with translation.override(lang):
					g.add((EOLAS_NS[self.category], rdflib.SKOS.prefLabel, rdflib.Literal(translation.gettext(self.category), lang=lang)))
		return g

	def get_absolute_url(self):
		# Synthetic families (qli for language isolates, qsp for ISO 639 special codes) don't
		# appear in iso639-5 or the library of congress list, so they need local URIs.
		LOCAL_FAMILY_CODES = {"qli", "qsp"}
		if self.pk in LOCAL_FAMILY_CODES:
			return f"{BASE_URL}/metadata/{self._meta.model_name}/{self.pk}/"
		# For other language families, use the library of congress URI
		else:
			return f"http://id.loc.gov/vocabulary/iso639-5/{self.pk}"

	def get_webhook_url(self):
		# Always use the eolas-hosted URL for webhooks, regardless of whether the
		# canonical identifier is the LoC URI. Arachne fetches this URL to retrieve
		# eolas's RDF — sending the LoC URI causes arachne to fetch LoC's JSON-LD,
		# which uses LoC-internal type vocabularies that fail arachne's validator.
		return f"{BASE_URL}/metadata/{self._meta.model_name}/{self.pk}/"

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
	)

	@property
	def type(self):
		return self.family

	class Meta:
		verbose_name = _('Language')
		verbose_name_plural = _('Languages')
		ordering = ["name"]

	indigenous_to = RDFManyToManyField(
		'Place',
		blank=True,
		related_name='indigenous_languages',
		verbose_name=_('indigenous to'),
		rdf_predicate=EOLAS_NS.languageIndigenousTo, # indigenous to
		rdf_label="Indigenous To",
		rdf_inverse_predicate=EOLAS_NS.indigenousLanguage,
		rdf_inverse_label="Indigenous Language",
	)
	widely_spoken_in = RDFManyToManyField(
		'Place',
		blank=True,
		related_name='widely_spoken_languages',
		verbose_name=_('widely spoken in'),
		rdf_predicate=EOLAS_NS.widelySpokenIn,
		rdf_label="Widely Spoken In",
		rdf_inverse_predicate=WDT_NS.P2936, # language used
		rdf_inverse_label="Language Used",
	)
	@classmethod
	def get_ontology_rdf(cls):
		g = rdflib.Graph()
		g.add((EOLAS_NS.languageIndigenousTo, rdflib.RDFS.subPropertyOf, WDT_NS.P2341))
		return g

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

	heritage_language = RDFManyToManyField(
		'Language',
		blank=True,
		related_name='heritage_groups',
		verbose_name=_('heritage language'),
		rdf_predicate=WDT_NS.P103, # native language
		rdf_label="Native Language",
		rdf_inverse_predicate=EOLAS_NS.heritageGroup,
		rdf_inverse_label="Heritage Group",
	)
	indigenous_to = RDFManyToManyField(
		'Place',
		blank=True,
		related_name='indigenous_groups',
		verbose_name=_('indigenous to'),
		rdf_predicate=EOLAS_NS.ethnicGroupIndigenousTo,
		rdf_label="Indigenous To",
		rdf_inverse_predicate=EOLAS_NS.indigenousGroup,
		rdf_inverse_label="Indigenous Group",
	)
	@classmethod
	def get_ontology_rdf(cls):
		g = rdflib.Graph()
		g.add((EOLAS_NS.ethnicGroupIndigenousTo, rdflib.RDFS.subPropertyOf, WDT_NS.P2341))
		return g

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

class CreativeWorkType(EolasModel):
	rdf_type = EOLAS_NS.CreativeWorkType
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
		verbose_name = _('Creative Work Type')
		verbose_name_plural = _('Creative Work Types')
		ordering = ["name"]

	def __str__(self):
		return self.name.title()

	def get_rdf(self, include_type_label):
		uri = rdflib.URIRef(self.get_absolute_url())
		g = super().get_rdf(include_type_label)
		g.add((uri, rdflib.RDFS.subClassOf, rdflib.SDO.CreativeWork))
		g.add((uri, EOLAS_NS.hasCategory, EOLAS_NS[self.category]))
		if include_type_label:
			for lang, _ in settings.LANGUAGES:
				with translation.override(lang):
					g.add((EOLAS_NS[self.category], rdflib.SKOS.prefLabel, rdflib.Literal(translation.gettext(self.category), lang=lang)))
		return g

class CreativeWork(EolasModel):
	rdf_type = rdflib.SDO.CreativeWork
	name = RDFNameField(unique=False)
	type = RDFForeignKey(
		CreativeWorkType,
		on_delete=models.RESTRICT,
		null=False,
		blank=False,
	)
	class Meta:
		verbose_name = _('Creative Work')
		verbose_name_plural = _('Creative Works')
		ordering = ["name"]
