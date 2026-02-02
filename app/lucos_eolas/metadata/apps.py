from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

class MetadataConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'lucos_eolas.metadata'
    verbose_name = _('Metadata')

    def ready(self):
        from django.db.models.signals import post_save, post_delete
        from .signals import metadata_post_save, metadata_post_delete

        for model in self.get_models():
            post_save.connect(metadata_post_save, sender=model, weak=False)
            post_delete.connect(metadata_post_delete, sender=model, weak=False)