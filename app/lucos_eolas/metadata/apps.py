import logging
import threading
import time

from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _

logger = logging.getLogger(__name__)


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

        self._start_check_refresh_thread()

    def _start_check_refresh_thread(self):
        """Start a daemon thread that recomputes info checks every 5 minutes."""
        def _loop():
            from .checks import refresh_check_cache
            while True:
                try:
                    refresh_check_cache()
                except Exception:
                    logger.exception("Background check refresh failed")
                time.sleep(300)  # 5 minutes

        thread = threading.Thread(target=_loop, daemon=True, name='eolas-check-refresh')
        thread.start()