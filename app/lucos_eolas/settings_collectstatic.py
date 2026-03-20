"""
Minimal settings for the collectstatic build step.

Only declares what collectstatic needs — no database, no auth, no
third-party apps that require environment variables at import time.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = 'build-time-placeholder'

INSTALLED_APPS = [
    'django.contrib.staticfiles',
]

STATIC_URL = '/resources/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "templates/resources"),
]
