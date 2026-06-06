from django.apps import apps
from django.db import transaction
from django.db.models.signals import post_save, post_delete
from loganne import updateLoganne

def metadata_post_save(sender, instance, created, **kwargs):
	item_type = instance._meta.verbose_name.title()
	event_type = "itemCreated" if created else "itemUpdated"
	human = f'{item_type} "{instance}" {"created" if created else "updated"}'
	url = instance.get_webhook_url()
	transaction.on_commit(
		lambda: updateLoganne(type=event_type, humanReadable=human, url=url, level="routine", itemType=item_type)
	)

def metadata_post_delete(sender, instance, **kwargs):
	item_type = instance._meta.verbose_name.title()
	human = f'{item_type} "{instance}" deleted'
	url = instance.get_webhook_url()
	transaction.on_commit(
		lambda: updateLoganne(type="itemDeleted", humanReadable=human, url=url, level="routine", itemType=item_type)
	)
