"""
Test-only settings: sets sensible defaults for env vars so tests can run
inside the Docker Compose test profile (db_test service).
"""
import os
os.environ.setdefault('APP_ORIGIN', 'http://localhost')
os.environ.setdefault('SECRET_KEY', 'testsecret')
os.environ.setdefault('ENVIRONMENT', 'test')
os.environ.setdefault('AUTH_ORIGIN', 'http://localhost')
os.environ.setdefault('SYSTEM', 'lucos_eolas')
os.environ.setdefault('LOGANNE_ENDPOINT', 'http://localhost')
os.environ.setdefault('CLIENT_KEYS', 'test=key')
os.environ.setdefault('POSTGRES_PASSWORD', 'testpassword')
from lucos_eolas.settings import *

# Connect to the dedicated test database container (not the production db service)
DATABASES['default']['HOST'] = 'db_test'
