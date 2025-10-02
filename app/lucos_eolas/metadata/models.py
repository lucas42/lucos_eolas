import os
from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.utils.translation import gettext_lazy as _

BASE_URL = os.environ.get("BASE_URL")

class PlaceType(models.Model):
	name = models.CharField(
		max_length=255,
		verbose_name=_('name'),
		null=False,
		blank=False,
		unique=True,
	)
	plural = models.CharField(
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
	name = models.CharField(
		max_length=255,
		verbose_name=_('name'),
	)
	type = models.ForeignKey(
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
	fictional = models.BooleanField(
		default=False,
		verbose_name=_('fictional'),
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
	name = models.CharField(
		max_length=255,
		verbose_name=_('name'),
		null=False,
		blank=False,
		unique=True,
	)
	order = models.IntegerField(
		verbose_name=_('order'),
		null=False,
		blank=False,
		unique=True,
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
	name = models.CharField(
		max_length=255,
		verbose_name=_('name'),
		null=False,
		blank=False,
		unique=True,
	)
	class Meta:
		verbose_name = _('Calendar')
		verbose_name_plural = _('Calendars')
		ordering = ["name"]

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/calendar/{self.pk}/"

class Month(models.Model):
	name = models.CharField(
		max_length=255,
		verbose_name=_('name'),
		null=False,
		blank=False,
	)
	calendar = models.ForeignKey(
		Calendar,
		on_delete=models.RESTRICT,
		null=False,
		blank=False,
	)
	order_in_calendar = models.IntegerField(
		verbose_name=_('order in calendar'),
		null=False,
		blank=False,
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
	name = models.CharField(
		max_length=255,
		verbose_name=_('name'),
		null=False,
		blank=False,
		unique=True,
	)
	day_of_month = models.IntegerField(
		verbose_name=_('day of month'),
		null=True,
		blank=True,
	)
	month = models.ForeignKey(
		Month,
		on_delete=models.RESTRICT,
		null=True,
		blank=True,
	)
	class Meta:
		verbose_name = _('Festival')
		verbose_name_plural = _('Festivals')
		ordering = ['name']

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/festival/{self.pk}/"

class Memory(models.Model):
	name = models.CharField(
		max_length=255,
		verbose_name=_('name'),
		null=False,
		blank=False,
		unique=True,
	)
	description = models.TextField(
		verbose_name=_('description'),
		null=False,
		blank=True,
	)
	year = models.IntegerField(
		verbose_name=_('year'),
		null=True,
		blank=True,
		help_text=_('Approximate year of the memory')
	)
	class Meta:
		verbose_name = _('Memory')
		verbose_name_plural = _('Memories')
		ordering = ["year", "name"]

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/memory/{self.pk}/"

class Number(models.Model):
	name = models.CharField(
		max_length=255,
		verbose_name=_('name'),
		null=False,
		blank=False,
		unique=True,
	)
	value = models.DecimalField(
		max_digits=32,
		decimal_places=2,
		verbose_name=_('value'),
		null=True,
		blank=True,
		help_text=_('Approximate value of this number, up to 2 decimal places')
	)
	class Meta:
		verbose_name = _('Number')
		verbose_name_plural = _('Numbers')
		ordering = ["value", "name"]

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/number/{self.pk}/"

class TransportMode(models.Model):
	name = models.CharField(
		max_length=255,
		verbose_name=_('name'),
		null=False,
		blank=False,
		unique=True,
	)
	class Meta:
		verbose_name = _('Mode of Transport')
		verbose_name_plural = _('Modes of Transport')
		ordering = ["name"]

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/transportmode/{self.pk}/"

class LanguageFamily(models.Model):
	code = models.CharField(
		max_length=3,
		primary_key=True,
		verbose_name=_('code'),
		help_text=_('A valid ISO 639-5 code')
		)
	name = models.CharField(
		max_length=255,
		verbose_name=_('name'),
		null=False,
		blank=False,
		unique=True,
	)
	class Meta:
		verbose_name = _('Language Family')
		verbose_name_plural = _('Language Families')
		ordering = ["code"]

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/languagefamily/{self.pk}/"

class Language(models.Model):
	code = models.CharField(
		max_length=3,
		primary_key=True,
		verbose_name=_('code'),
		help_text=_('A valid ISO 639-3 code')
		)
	name = models.CharField(
		max_length=255,
		verbose_name=_('name'),
		null=False,
		blank=False,
		unique=True,
	)
	family = models.ForeignKey(
		LanguageFamily,
		on_delete=models.RESTRICT,
		null=False,
		blank=False,
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
	name = models.CharField(
		max_length=255,
		verbose_name=_('name'),
		null=False,
		blank=False,
		unique=True,
	)
	wikipedia_slug = models.CharField(
		max_length=255,
		verbose_name=_('Wikipedia URL Slug'),
		help_text=_('The URL Slug used by the primary page regarding this event on the English Language instance of Wikipedia'),
		unique=True,
	)
	year = models.IntegerField(
		verbose_name=_('year'),
		null=True,
		blank=True,
		help_text=_('Approximate year of the event, in the Gregorian Calendar')
	)
	class Meta:
		verbose_name = _('Historical Event')
		verbose_name_plural = _('Historical Events')
		ordering = ["year", "name"]

	def __str__(self):
		return self.name

	def get_absolute_url(self):
		return f"{BASE_URL}metadata/historicalevent/{self.pk}/"
