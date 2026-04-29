"""
Minimal settings for the collectstatic build step.

Only declares what collectstatic needs — no database, no auth, no
third-party apps that require environment variables at import time.

`django.contrib.admin` (and its prerequisites `auth` and `contenttypes`)
must be present so that `collectstatic` includes the Django admin
CSS/JS/image assets — eolas's UI is the Django admin, so without these
every page renders unstyled.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

SECRET_KEY = 'build-time-placeholder'

INSTALLED_APPS = [
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.admin',
    'django.contrib.staticfiles',
]

STATIC_URL = '/resources/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static')
STATICFILES_DIRS = [
    os.path.join(BASE_DIR, "templates/resources"),
]
