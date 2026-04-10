"""
Test-only settings: sets sensible defaults for env vars so tests can run
inside a Docker Compose environment with a real PostgreSQL db service.
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
