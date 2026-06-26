# lucosauth has no database models — the Django auth User model (django.contrib.auth)
# is used directly. This file is intentionally minimal.
#
# The old LucosAuthBackend (lucos_authentication token-introspection) has been
# replaced by AithneAuthMiddleware + verify_aithne_token (ADR-0002).
from django.db import models  # noqa: F401 — keeps Django's app-discovery happy
