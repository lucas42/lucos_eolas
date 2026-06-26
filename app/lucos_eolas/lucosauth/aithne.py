"""
JWKS/JWT verification for aithne sessions (ADR-0002).

This module implements the per-request local JWT verification used by
AithneAuthMiddleware and @require_scope. It is the Django-specific
instantiation of the lucos_aithne local-verification-contract.

Public API:
  verify_aithne_token(token_str) -> (principal_class, sub, scopes) or None
  map_principal(request, principal_class, sub, scopes) -> None
"""

import logging
import os
import re
import threading

import jwt
from jwt import PyJWKClient, PyJWKClientError

logger = logging.getLogger(__name__)

# Import PyJWKClientNetworkError if available (PyJWT >= 2.4.0); fall back to
# the base class so the except clause still catches network failures.
try:
    from jwt import PyJWKClientNetworkError
except ImportError:
    PyJWKClientNetworkError = PyJWKClientError

_AITHNE_ORIGIN = os.environ.get("AITHNE_ORIGIN", "https://aithne.l42.eu")
# AITHNE_JWKS_URL overrides the JWKS fetch URL (server-side container address
# in dev); it must NOT influence the iss check or login redirect — both derive
# from AITHNE_ORIGIN only.
_AITHNE_JWKS_URL = os.environ.get("AITHNE_JWKS_URL") or f"{_AITHNE_ORIGIN}/.well-known/jwks.json"
_AITHNE_ISSUER = _AITHNE_ORIGIN
_AITHNE_AUDIENCE = "l42.eu"


class _LKGJWKSClient:
    """PyJWKClient wrapper that serves last-known-good keys on network failure.

    On a JWKS-fetch or connection error, falls back to the last successfully
    fetched signing key set. If no key has ever been fetched (cold start),
    fails closed — the token is rejected and the caller treats the request as
    unauthenticated (→ login redirect / 403). This is correct and deliberate:
    the fail-closed cold-start case must NOT be 'fixed' by skipping verification.
    """

    def __init__(self, uri):
        self._client = PyJWKClient(uri, cache_keys=True, lifespan=300)
        self._last_good_key = None
        self._lock = threading.Lock()

    def get_signing_key_from_jwt(self, token):
        try:
            key = self._client.get_signing_key_from_jwt(token)
            with self._lock:
                self._last_good_key = key
            return key
        except PyJWKClientNetworkError as e:
            # Network / fetch failure — fall back to last-known-good.
            with self._lock:
                fallback = self._last_good_key
            if fallback is None:
                # Cold start with no cached key: fail closed.
                raise
            safe_msg = re.sub(r'[\x00-\x1f\x7f]', '', str(e))
            logger.warning("JWKS fetch failed (using last-known-good): %s", safe_msg)
            return fallback
        # Any other PyJWKClientError (e.g. kid not found after refresh) propagates normally.


# Module-level client shared across all requests.
_jwks_client = _LKGJWKSClient(_AITHNE_JWKS_URL)


def _set_jwks_client(client):
    """Override the JWKS client. For testing only — do not call in production."""
    global _jwks_client
    _jwks_client = client


def verify_aithne_token(token_str):
    """Verify an aithne-issued JWT.

    Returns a (principal_class, sub, scopes) tuple on success, or None on any
    failure (bad signature, expired, unknown principal_class, etc.).

    Implements local-verification-contract §1–6:
    - ES256 with algorithm pinning (never trust the header alg field)
    - iss == AITHNE_ORIGIN
    - aud contains l42.eu
    - exp/iat with 30-second leeway
    - requires exp/iat/sub claims
    - accepts principal_class 'human' or 'agent' only
    """
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token_str)
        payload = jwt.decode(
            token_str,
            signing_key.key,
            algorithms=["ES256"],  # pin to ES256 — defence-in-depth vs algorithm confusion
            issuer=_AITHNE_ISSUER,
            audience=_AITHNE_AUDIENCE,
            leeway=30,  # 30-second clock-skew tolerance per local-verification-contract
            options={"require": ["exp", "iat", "sub"]},
        )
        principal_class = payload.get("principal_class")
        if principal_class not in ("human", "agent"):
            safe_pc = re.sub(r'[\x00-\x1f\x7f]', '', str(principal_class))
            logger.debug("JWT has unknown principal_class: %r", safe_pc)
            return None
        scopes = payload.get("scopes") or []
        sub = payload["sub"]
        return (principal_class, sub, scopes)
    except Exception:
        # Expected noise: expired, bad signature, etc. Log at DEBUG only.
        logger.debug("JWT verification failed: %s", type(Exception).__name__)
        return None


def map_principal(request, principal_class, sub, scopes):
    """Map a verified JWT principal to a Django user and set request.user.

    human  → User.objects.get_or_create(id=sub); is_staff/is_superuser from
             eolas:admin scope; dev render-ui GET/HEAD also grants is_staff.

    agent  → No persistent Django user. In development, render-ui scope on
             GET/HEAD grants staff access to the Django admin so lucos-ux can
             snapshot pages. Production: leaves request.user as AnonymousUser.

    is_staff = is_superuser are both derived from the eolas:admin scope
    (replacing the hardcoded id == '2' check — ADR-0002 §6).
    """
    from django.contrib.auth.models import User

    has_admin = "eolas:admin" in scopes
    env = os.environ.get("ENVIRONMENT", "production")
    is_render_ui_read = (
        env == "development"
        and "render-ui" in scopes
        and request.method in ("GET", "HEAD")
    )

    if principal_class == "human":
        user, _ = User.objects.get_or_create(id=sub)
        user.is_staff = has_admin or is_render_ui_read
        user.is_superuser = has_admin
        # Allow Django's auth decorators to use this user without going through
        # the authentication backend.
        user.backend = "django.contrib.auth.backends.ModelBackend"
        request.user = user

    elif principal_class == "agent":
        if is_render_ui_read:
            # Dev only: create a synthetic staff user for this agent slug so
            # lucos-ux can access the Django admin read-only. The username is
            # prefixed to distinguish from human users. Never runs in production.
            username = f"agent:{sub[:140]}"
            user, _ = User.objects.get_or_create(
                username=username,
                defaults={"is_staff": True, "is_superuser": False},
            )
            user.is_staff = True
            user.is_superuser = False
            user.backend = "django.contrib.auth.backends.ModelBackend"
            request.user = user
        # Otherwise: leave request.user as AnonymousUser. Agents authorised
        # by scope proceed via @require_scope on individual views; without
        # render-ui they cannot reach the admin (correct).


def get_aithne_origin():
    """Return the AITHNE_ORIGIN value for use in templates and redirects.

    Always reads from the environment (not cached at module load) so that
    tests can control it by setting os.environ directly.
    """
    return os.environ.get("AITHNE_ORIGIN", "https://aithne.l42.eu")
