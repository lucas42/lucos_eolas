from django.apps import apps
from django.db.models.signals import post_save, post_delete
from .loganne import loganneRequest

def metadata_post_save(sender, instance, created, **kwargs):
	item_type = instance._meta.verbose_name.title()
	if created:
		loganneRequest({
			"type": "itemCreated",
			"humanReadable": f'{item_type} "{instance}" created',
			"url": instance.get_absolute_url(),
		})
	else:
		loganneRequest({
			"type": "itemUpdated",
			"humanReadable": f'{item_type} "{instance}" updated',
			"url": instance.get_absolute_url(),
		})

def metadata_post_delete(sender, instance, **kwargs):
	item_type = instance._meta.verbose_name.title()
	loganneRequest({
		"type": "itemDeleted",
		"humanReadable": f'{item_type} "{instance}" deleted',
		"url": instance.get_absolute_url(),
	})
