"""
JWKS/JWT verification for aithne sessions (ADR-0002).

Public API:
  verify_aithne_token(token_str)                      -> (principal_class, sub, scopes) or None
  map_principal(request, principal_class, sub, scopes) -> None
  aithne_login_redirect(request, next_path=None)       -> HttpResponseRedirect
  aithne_unavailable_response(request)                 -> HttpResponse (503, local page)
  is_aithne_reachable()                                -> bool
  get_aithne_origin()                                  -> str
"""

import logging
import os
import re
import threading
from urllib.parse import urlencode

import jwt
from jwt import PyJWKClient, PyJWKClientError

logger = logging.getLogger(__name__)

# PyJWT exports PyJWKClientConnectionError (added in 2.8.0) specifically for a
# JWKS fetch failing due to a connection/network error — as opposed to the
# broader PyJWKClientError, which also covers e.g. "kid not found" once the
# endpoint has been reached successfully.  (PyJWKClientNetworkError never
# existed in PyJWT's public API — the name below is kept only as our own
# internal alias for readability at call sites.)  Older PyJWT versions before
# 2.8.0 don't export it — fall back to the base class so the except clauses
# below still catch *something*, though at that point they can no longer
# distinguish a genuine network failure from other JWKS client errors.
try:
    from jwt import PyJWKClientConnectionError as PyJWKClientNetworkError
except ImportError:
    PyJWKClientNetworkError = PyJWKClientError

_AITHNE_ORIGIN = os.environ.get("AITHNE_ORIGIN", "https://aithne.l42.eu")
# AITHNE_JWKS_URL overrides the JWKS fetch address (e.g. Docker bridge IP in dev).
# It must NOT influence the iss check or ?next= redirect — both derive from
# AITHNE_ORIGIN only.
_AITHNE_JWKS_URL = os.environ.get("AITHNE_JWKS_URL") or f"{_AITHNE_ORIGIN}/.well-known/jwks.json"
_AITHNE_ISSUER = _AITHNE_ORIGIN
_AITHNE_AUDIENCE = "l42.eu"


class _LKGJWKSClient:
    """PyJWKClient wrapper that serves last-known-good keys on network failure.

    Falls back to the last successfully fetched signing key when a network
    error occurs.  Cold-start (no cached key) fails closed — the token is
    rejected and the caller treats the request as unauthenticated.

    Also tracks whether the *most recent* fetch attempt hit a network error
    (`_unreachable`), regardless of whether a last-known-good key let
    verification succeed anyway.  This is a best-effort reachability signal
    for aithne itself (see `is_aithne_reachable()` below) — it is only ever
    updated when a token is actually presented for verification, so it can
    lag reality until the next token-bearing request comes in.
    """

    def __init__(self, uri):
        self._client = PyJWKClient(uri, cache_keys=True, lifespan=300)
        self._last_good_key = None
        self._unreachable = False
        self._lock = threading.Lock()

    def get_signing_key_from_jwt(self, token):
        try:
            key = self._client.get_signing_key_from_jwt(token)
            with self._lock:
                self._last_good_key = key
                self._unreachable = False
            return key
        except PyJWKClientNetworkError as e:
            with self._lock:
                fallback = self._last_good_key
                self._unreachable = True
            safe_msg = re.sub(r'[\x00-\x1f\x7f]', '', str(e))
            if fallback is None:
                logger.warning("JWKS fetch failed at cold start (no cached key — failing closed): %s", safe_msg)
                raise
            logger.warning("JWKS fetch failed (using last-known-good): %s", safe_msg)
            return fallback
        # Any other PyJWKClientError (e.g. kid not found after refresh) propagates normally —
        # that means the JWKS endpoint WAS reached, so it doesn't affect _unreachable.

    def is_unreachable(self):
        with self._lock:
            return self._unreachable


# Module-level client shared across all requests.
_jwks_client = _LKGJWKSClient(_AITHNE_JWKS_URL)


def _set_jwks_client(client):
    """Override the JWKS client. For testing only — do not call in production."""
    global _jwks_client
    _jwks_client = client


def get_aithne_origin():
    """Return AITHNE_ORIGIN, always fresh from the environment (testable)."""
    return os.environ.get("AITHNE_ORIGIN", "https://aithne.l42.eu")


def is_aithne_reachable():
    """Best-effort signal for whether aithne is currently reachable.

    Backed by `_LKGJWKSClient.is_unreachable()` — see that class's docstring
    for what "best-effort" means here.  Used to decide whether it's safe to
    redirect an unauthenticated visitor to aithne's login page, or whether
    that redirect would just hand them a dead link.
    """
    return not _jwks_client.is_unreachable()


def verify_aithne_token(token_str):
    """Verify an aithne-issued JWT.

    Returns a (principal_class, sub, scopes) tuple on success, or None on any
    failure (bad signature, expired, missing claims, etc.).

    - ES256 with algorithm pinning (never trust the header alg field)
    - iss == AITHNE_ORIGIN, aud contains l42.eu
    - exp/iat with 30-second clock-skew leeway; exp/iat/sub required
    """
    # Phase 1 — resolve signing key from JWKS.  Network/parse failures are
    # logged with specific messages by _LKGJWKSClient; we just surface them here.
    # Note: get_signing_key_from_jwt also decodes the JWT header to extract the
    # kid, so malformed tokens (too few segments, invalid base64, etc.) raise
    # jwt.DecodeError here, before we even reach jwt.decode() in phase 2.
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token_str)
    except PyJWKClientNetworkError:
        # _LKGJWKSClient already logged a WARNING for this case (cold-start
        # or fallback exhausted).  Treat as unauthenticated.
        logger.warning("JWT rejected: JWKS unreachable and no cached key available")
        return None
    except PyJWKClientError as exc:
        logger.warning("JWT rejected: JWKS client error (%s: %s)", type(exc).__name__, exc)
        return None
    except jwt.DecodeError as exc:
        logger.warning("JWT rejected: malformed token (can't parse header) — %s", exc)
        return None

    # Phase 2 — decode and validate the JWT payload.
    try:
        payload = jwt.decode(
            token_str,
            signing_key.key,
            algorithms=["ES256"],
            issuer=_AITHNE_ISSUER,
            audience=_AITHNE_AUDIENCE,
            leeway=30,
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        logger.warning("JWT rejected: token has expired")
        return None
    except jwt.InvalidIssuerError:
        logger.warning("JWT rejected: wrong issuer (expected '%s')", _AITHNE_ISSUER)
        return None
    except jwt.InvalidAudienceError:
        logger.warning("JWT rejected: wrong audience (expected '%s')", _AITHNE_AUDIENCE)
        return None
    except jwt.MissingRequiredClaimError as exc:
        logger.warning("JWT rejected: missing required claim — %s", exc)
        return None
    except jwt.DecodeError as exc:
        logger.warning("JWT rejected: decode error — %s", exc)
        return None
    except jwt.InvalidTokenError as exc:
        logger.warning("JWT rejected: %s — %s", type(exc).__name__, exc)
        return None

    principal_class = payload.get("principal_class")
    scopes = payload.get("scopes") or []
    sub = payload["sub"]
    logger.debug(
        "JWT verified: principal_class=%s sub=%.30s scopes=%s",
        principal_class, sub, scopes,
    )
    return (principal_class, sub, scopes)


def map_principal(request, principal_class, sub, scopes):
    """Map a verified JWT principal to a Django user and populate request.user.

    Authorization is scope-only (ADR-0002 §4/§6): is_staff and is_superuser
    are derived from scopes, never from principal_class.  principal_class is
    used only to identify the principal in log output.
    """
    from django.contrib.auth.models import User

    has_admin = "eolas:admin" in scopes
    env = os.environ.get("ENVIRONMENT", "production")
    is_render_ui_read = (
        env == "development"
        and "render-ui" in scopes
        and request.method in ("GET", "HEAD")
    )

    user, created = User.objects.get_or_create(username=sub)
    user.is_staff = has_admin or is_render_ui_read
    user.is_superuser = has_admin
    # Allow Django's auth decorators to accept this user without going through
    # a full authentication backend.
    user.backend = "django.contrib.auth.backends.ModelBackend"
    request.user = user
    logger.debug(
        "Mapped %s '%s' → pk=%s staff=%s superuser=%s",
        principal_class, sub[:30], user.pk, user.is_staff, user.is_superuser,
    )


def aithne_login_redirect(request, next_path=None):
    """Return a redirect to the aithne login page.

    next_path: local path to return to after login (default: request.path).
    A full URL is built from next_path so aithne knows which origin to
    redirect back to after authentication.
    """
    from django.shortcuts import redirect

    path = next_path if next_path is not None else request.path
    next_url = request.build_absolute_uri(path)
    aithne_origin = get_aithne_origin()
    login_url = f"{aithne_origin}/auth/login?{urlencode({'next': next_url})}"
    logger.debug("Redirecting to aithne login (next=%s)", next_url)
    return redirect(login_url)


def aithne_unavailable_response(request):
    """Return a local, lucos_eolas-branded "sign-in unavailable" page.

    Used instead of aithne_login_redirect() when aithne itself is known to be
    unreachable — redirecting to a dead aithne just hands the visitor their
    browser's own "can't reach this page" error, with no explanation and no
    retry guidance.  Returns 503 (Service Unavailable): sign-in genuinely
    can't proceed right now, and it isn't the visitor's fault.

    Rendered as inline HTML rather than a template, matching the existing
    403 pages in decorators.py / metadata/admin.py — this repo has no
    non-admin base template to extend.
    """
    from django.http import HttpResponse

    logger.warning(
        "aithne unreachable — rendering local sign-in-unavailable page for %s instead of redirecting",
        request.path,
    )
    return HttpResponse(
        "<html><head><title>Sign-in unavailable</title>"
        "<meta charset=\"utf-8\"></head><body>"
        "<p>Sign-in is temporarily unavailable. Try again in a few minutes.</p>"
        "<pre>Couldn't reach the authentication service (aithne) to verify your session.</pre>"
        "</body></html>",
        status=503,
        content_type="text/html; charset=utf-8",
    )
