"""
Test-only settings: overrides the database to use SQLite in-memory
so tests can run without a live PostgreSQL server.
"""
import os
os.environ.setdefault('POSTGRES_PASSWORD', 'unused-in-tests')
from lucos_eolas.settings import *

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }
}
