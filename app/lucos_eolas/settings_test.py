"""
Test-only settings: overrides the database to use SQLite in-memory
so tests can run without a live PostgreSQL server.
"""
import os
os.environ.setdefault('APP_ORIGIN', 'http://localhost')
os.environ.setdefault('SECRET_KEY', 'testsecret')
os.environ.setdefault('ENVIRONMENT', 'test')
os.environ.setdefault('AUTH_ORIGIN', 'http://localhost')
os.environ.setdefault('SYSTEM', 'lucos_eolas')
os.environ.setdefault('LOGANNE_ENDPOINT', 'http://localhost')
os.environ.setdefault('CLIENT_KEYS', 'test=key')
os.environ.setdefault('POSTGRES_PASSWORD', 'unused-in-tests')
from lucos_eolas.settings import *

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}
