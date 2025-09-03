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
		verbose_name = _('place type')
		verbose_name_plural = _('place types')

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
		verbose_name = _('place')
		verbose_name_plural = _('places')

	def __str__(self):
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
		verbose_name = _('day of the week')
		verbose_name_plural = _('days of the week')

	def __str__(self):
		return self.name
