"""
Populate-only aithne authentication middleware (ADR-0002 §2).

Reads the aithne_session cookie (humans) or an Authorization: Bearer <aithne JWT>
header (agents, e.g. lucos-ux which cannot receive the Secure Domain=l42.eu cookie
on http://localhost), verifies the token, and populates request.user.

The middleware NEVER blocks — it only populates request.user, exactly as Django's
own AuthenticationMiddleware does. This gives the /_info exemption for free:
enforcement lives at the view (@require_scope), not here.

JWT-present-but-invalid behaviour
----------------------------------
When an aithne_session cookie or Bearer header IS present but verification fails
(expired, bad signature, unknown kid, etc.), the middleware resets request.user to
AnonymousUser. A bad JWT is not a fallback-to-session signal — it indicates the
principal should re-authenticate rather than silently continue as a session user.

No-JWT behaviour
----------------
When no JWT cookie or header is present, request.user is left as-is from
AuthenticationMiddleware (which may have populated it from a Django session). This
allows Django test clients that use force_login() to keep working, and provides a
graceful transition window where existing sessions continue until they expire
naturally (login() is no longer called, so no new sessions are minted).
"""

import logging

from django.contrib.auth.models import AnonymousUser

from .aithne import verify_aithne_token, map_principal

logger = logging.getLogger(__name__)


class AithneAuthMiddleware:
    """Populate request.user from the aithne_session cookie or Bearer JWT.

    When a JWT token is present and valid, sets request.user from the verified
    token payload. When the token is present but invalid, resets request.user to
    AnonymousUser. When no token is present, leaves request.user as-is.

    Must be registered after django.contrib.auth.middleware.AuthenticationMiddleware
    in MIDDLEWARE.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.aithne_scopes = []

        token, source = self._extract_token(request)
        if token:
            logger.debug("aithne token found via %s on %s", source, request.path)
            # JWT present — take ownership of request.user.
            # Always reset first so an invalid/expired token never falls back to
            # a session-populated user.
            request.user = AnonymousUser()
            result = verify_aithne_token(token)
            if result is not None:
                principal_class, sub, scopes = result
                request.aithne_scopes = scopes
                map_principal(request, principal_class, sub, scopes)
            else:
                logger.warning(
                    "aithne token present (via %s) but verification failed — "
                    "treating %s as unauthenticated (see rejection reason above)",
                    source, request.path,
                )
        else:
            logger.debug("No aithne token on %s — proceeding as anonymous", request.path)
        # No JWT: leave request.user as set by AuthenticationMiddleware (session auth).

        return self.get_response(request)

    @staticmethod
    def _extract_token(request):
        """Return (token, source) where source names where the token came from.

        Returns (None, None) when no aithne JWT is present.

        Prefers the aithne_session cookie (set domain-wide by aithne for
        browser sessions). Falls back to Authorization: Bearer <token> for
        agents (e.g. lucos-ux) that cannot receive the Secure l42.eu cookie
        on http://localhost in development.

        The Bearer header here carries an aithne JWT — not a lucos_creds API
        key. The existing @api_auth path (lucos_creds keys) is unchanged and
        out of scope for this middleware.
        """
        # Cookie path — human sessions
        cookie = request.COOKIES.get("aithne_session")
        if cookie:
            return cookie, "aithne_session cookie"

        # Bearer header path — agents in development
        auth_header = request.META.get("HTTP_AUTHORIZATION", "")
        if auth_header.lower().startswith("bearer "):
            return auth_header[7:].strip(), "Bearer header"

        return None, None
