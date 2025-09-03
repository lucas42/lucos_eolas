from django.db import models
from django.contrib.postgres.fields import ArrayField
from django.utils.translation import gettext_lazy as _

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

	def __str__(self):
		return self.name.title()

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

	def __str__(self):
		# Build a queryset matching either exact name or element in alternate_names
		qs = Place.objects.filter(
			models.Q(name__iexact=self.name) |
			models.Q(alternate_names__contains=[self.name])
		)

		if qs.count() > 1:
			return f"{self.name} ({self.type.name.title()})"

		return self.name

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

	def __str__(self):
		return self.name

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

	def __str__(self):
		return self.name

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
		return self.name
