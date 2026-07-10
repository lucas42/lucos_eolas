from django.test import SimpleTestCase, RequestFactory, TestCase, override_settings
from unittest.mock import patch, MagicMock
from django.http import HttpResponse
from django.contrib.auth.models import AnonymousUser
from .decorators import api_auth, require_scope
from .views import loginview
from .middleware import AithneAuthMiddleware


def _make_view():
    """Return a simple decorated view that records whether it was called."""
    @api_auth
    def view(request):
        return HttpResponse(status=200)
    return view


def _make_request(auth_header=None):
    request = MagicMock()
    request.META = {}
    if auth_header is not None:
        request.META['HTTP_AUTHORIZATION'] = auth_header
    return request


VALID_KEY = 'testkey123'
MOCK_USER = MagicMock()


# ---------------------------------------------------------------------------
# LoginView tests — new aithne-redirect behaviour
# ---------------------------------------------------------------------------

class LoginViewAithneRedirectTest(SimpleTestCase):
    """The login view is now a plain redirect to aithne (no token handling)."""

    def setUp(self):
        self.factory = RequestFactory()

    def _call(self, url, aithne_origin='http://aithne.test'):
        request = self.factory.get(url)
        with patch.dict('os.environ', {'AITHNE_ORIGIN': aithne_origin}):
            return loginview(request)

    def test_no_next_redirects_to_aithne_login(self):
        response = self._call('/login')
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login', response['Location'])

    def test_same_origin_next_is_preserved(self):
        response = self._call('/login?next=/some/page/')
        self.assertEqual(response.status_code, 302)
        # ?next= is now a full URL so aithne can redirect back to the right origin
        location = response['Location']
        self.assertIn('next=', location)
        self.assertIn('some%2Fpage%2F', location)

    def test_external_next_is_replaced_with_root(self):
        response = self._call('/login?next=https://evil.example.com/')
        self.assertEqual(response.status_code, 302)
        location = response['Location']
        # External ?next= must be rejected — must not appear in the redirect
        self.assertNotIn('evil.example.com', location)

    def test_redirect_uses_aithne_origin(self):
        response = self._call('/login', aithne_origin='http://aithne.test')
        self.assertTrue(response['Location'].startswith('http://aithne.test/auth/login'))

    def test_no_longer_handles_token_param(self):
        """The old ?token= flow is gone — redirect must not include the raw token."""
        request = self.factory.get('/login?token=sometoken')
        with patch.dict('os.environ', {'AITHNE_ORIGIN': 'http://aithne.test'}):
            response = loginview(request)
        # Redirect target must NOT forward the token
        self.assertNotIn('token=sometoken', response['Location'])


# ---------------------------------------------------------------------------
# AithneAuthMiddleware tests
# ---------------------------------------------------------------------------

class AithneMiddlewareTest(SimpleTestCase):
    """AithneAuthMiddleware is populate-only — never blocks."""

    def setUp(self):
        self.factory = RequestFactory()
        self.get_response = MagicMock(return_value=HttpResponse(status=200))

    def _get_middleware(self):
        return AithneAuthMiddleware(self.get_response)

    def _make_request(self, cookie=None, auth_header=None, path='/'):
        request = self.factory.get(path)
        request.user = AnonymousUser()
        request.aithne_scopes = []
        if cookie:
            request.COOKIES['aithne_session'] = cookie
        if auth_header:
            request.META['HTTP_AUTHORIZATION'] = auth_header
        return request

    def test_no_token_leaves_anonymous_user(self):
        mw = self._get_middleware()
        request = self._make_request()
        with patch('lucos_eolas.lucosauth.middleware.verify_aithne_token', return_value=None):
            mw(request)
        self.assertIsInstance(request.user, AnonymousUser)

    def test_no_token_still_calls_view(self):
        """Middleware never blocks — it always calls get_response."""
        mw = self._get_middleware()
        request = self._make_request()
        with patch('lucos_eolas.lucosauth.middleware.verify_aithne_token', return_value=None):
            mw(request)
        self.get_response.assert_called_once()

    def test_valid_cookie_token_calls_verify_and_map(self):
        mw = self._get_middleware()
        request = self._make_request(cookie='valid.jwt.token')
        with patch('lucos_eolas.lucosauth.middleware.verify_aithne_token',
                   return_value=('human', 'user123', ['eolas:admin'])) as mock_verify, \
             patch('lucos_eolas.lucosauth.middleware.map_principal') as mock_map:
            mw(request)
        mock_verify.assert_called_once_with('valid.jwt.token')
        mock_map.assert_called_once_with(request, 'human', 'user123', ['eolas:admin'])

    def test_valid_bearer_token_calls_verify_and_map(self):
        mw = self._get_middleware()
        request = self._make_request(auth_header='Bearer valid.jwt.token')
        with patch('lucos_eolas.lucosauth.middleware.verify_aithne_token',
                   return_value=('agent', 'lucos-ux', ['render-ui'])) as mock_verify, \
             patch('lucos_eolas.lucosauth.middleware.map_principal') as mock_map:
            mw(request)
        mock_verify.assert_called_once_with('valid.jwt.token')

    def test_cookie_takes_priority_over_bearer(self):
        mw = self._get_middleware()
        request = self._make_request(
            cookie='cookie.jwt.token',
            auth_header='Bearer bearer.jwt.token',
        )
        with patch('lucos_eolas.lucosauth.middleware.verify_aithne_token',
                   return_value=None) as mock_verify, \
             patch('lucos_eolas.lucosauth.middleware.map_principal'):
            mw(request)
        mock_verify.assert_called_once_with('cookie.jwt.token')

    def test_invalid_token_leaves_anonymous(self):
        mw = self._get_middleware()
        request = self._make_request(cookie='bad.jwt')
        with patch('lucos_eolas.lucosauth.middleware.verify_aithne_token', return_value=None):
            mw(request)
        self.assertIsInstance(request.user, AnonymousUser)

    def test_scopes_populated_on_request_on_success(self):
        mw = self._get_middleware()
        request = self._make_request(cookie='valid.jwt.token')

        mock_user = MagicMock()
        mock_user.is_authenticated = True

        def fake_map(req, pc, sub, scopes):
            req.user = mock_user

        with patch('lucos_eolas.lucosauth.middleware.verify_aithne_token',
                   return_value=('human', 'u1', ['eolas:admin'])), \
             patch('lucos_eolas.lucosauth.middleware.map_principal', side_effect=fake_map):
            mw(request)
        self.assertEqual(request.aithne_scopes, ['eolas:admin'])


# ---------------------------------------------------------------------------
# @require_scope decorator tests
# ---------------------------------------------------------------------------

class RequireScopeDecoratorTest(SimpleTestCase):
    """@require_scope enforces the three-branch pattern (ADR-0002 §4)."""

    def setUp(self):
        self.factory = RequestFactory()

    def _make_protected_view(self, scope='eolas:admin'):
        @require_scope(scope)
        def view(request):
            return HttpResponse(status=200)
        return view

    def _make_auth_request(self, scopes=None, authenticated=True, path='/admin/'):
        request = self.factory.get(path)
        if authenticated:
            user = MagicMock()
            user.is_authenticated = True
            request.user = user
        else:
            request.user = AnonymousUser()
        request.aithne_scopes = scopes or []
        return request

    def test_valid_token_with_required_scope_proceeds(self):
        """Branch 1: valid token + scope → 200."""
        view = self._make_protected_view('eolas:admin')
        request = self._make_auth_request(scopes=['eolas:admin'])
        response = view(request)
        self.assertEqual(response.status_code, 200)

    def test_valid_token_missing_scope_returns_403(self):
        """Branch 2: valid token, scope absent → styled 403."""
        view = self._make_protected_view('eolas:admin')
        request = self._make_auth_request(scopes=['eolas:read'])
        response = view(request)
        self.assertEqual(response.status_code, 403)

    def test_403_body_names_missing_scope(self):
        """The 403 body must name the required scope."""
        view = self._make_protected_view('eolas:admin')
        request = self._make_auth_request(scopes=[])
        response = view(request)
        self.assertEqual(response.status_code, 403)
        self.assertIn(b'eolas:admin', response.content)

    def test_no_token_redirects_to_aithne_login(self):
        """Branch 3: no valid token → redirect to aithne login."""
        view = self._make_protected_view('eolas:admin')
        request = self._make_auth_request(authenticated=False)
        with patch.dict('os.environ', {'AITHNE_ORIGIN': 'http://aithne.test'}):
            response = view(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn('http://aithne.test/auth/login', response['Location'])

    def test_redirect_includes_next_param(self):
        """Login redirect must include the current URL as ?next= (full URL, not path)."""
        view = self._make_protected_view('eolas:admin')
        request = self._make_auth_request(authenticated=False, path='/admin/metadata/')
        with patch.dict('os.environ', {'AITHNE_ORIGIN': 'http://aithne.test'}):
            response = view(request)
        location = response['Location']
        self.assertIn('next=', location)
        # next= must be a full URL (testserver is the RequestFactory host)
        self.assertIn('testserver', location)
        self.assertIn('admin%2Fmetadata%2F', location)

    def test_valid_token_empty_scopes_returns_403(self):
        """Authenticated principal with no scopes → 403 (not redirect)."""
        view = self._make_protected_view('eolas:admin')
        request = self._make_auth_request(scopes=[])
        response = view(request)
        self.assertEqual(response.status_code, 403)

    def test_different_scope_name_works(self):
        """@require_scope works with any scope string, not just eolas:admin."""
        @require_scope('eolas:read')
        def view(request):
            return HttpResponse(status=200)

        request = self._make_auth_request(scopes=['eolas:read'])
        response = view(request)
        self.assertEqual(response.status_code, 200)

    def test_valid_token_wrong_scope_not_redirected(self):
        """Branch 2 (403) — not branch 3 (redirect) — when authenticated but missing scope."""
        view = self._make_protected_view('eolas:admin')
        request = self._make_auth_request(authenticated=True, scopes=['some:other'])
        response = view(request)
        # Must be 403, not 302 — re-login cannot grant a scope the principal doesn't have.
        self.assertEqual(response.status_code, 403)


# ---------------------------------------------------------------------------
# @api_auth decorator tests (unchanged from before — regression coverage)
# ---------------------------------------------------------------------------

class ApiAuthDecoratorTest(SimpleTestCase):

    def _call(self, auth_header):
        view = _make_view()
        request = _make_request(auth_header)
        with patch('lucos_eolas.lucosauth.decorators.getUserByKey', return_value=MOCK_USER):
            return view(request), request

    def _call_bad_key(self, auth_header):
        view = _make_view()
        request = _make_request(auth_header)
        with patch('lucos_eolas.lucosauth.decorators.getUserByKey', return_value=None):
            return view(request), request

    def test_no_auth_header_returns_401(self):
        view = _make_view()
        request = _make_request()
        response = view(request)
        self.assertEqual(response.status_code, 401)

    def test_malformed_auth_header_returns_400(self):
        view = _make_view()
        request = _make_request('justonetoken')
        response = view(request)
        self.assertEqual(response.status_code, 400)

    def test_key_scheme_valid_key_succeeds(self):
        response, request = self._call(f'key {VALID_KEY}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(request.user, MOCK_USER)

    def test_key_scheme_uppercase_succeeds(self):
        response, request = self._call(f'KEY {VALID_KEY}')
        self.assertEqual(response.status_code, 200)

    def test_bearer_scheme_valid_key_succeeds(self):
        response, request = self._call(f'Bearer {VALID_KEY}')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(request.user, MOCK_USER)

    def test_bearer_scheme_lowercase_succeeds(self):
        response, request = self._call(f'bearer {VALID_KEY}')
        self.assertEqual(response.status_code, 200)

    def test_key_scheme_invalid_key_returns_403(self):
        response, _ = self._call_bad_key(f'key badkey')
        self.assertEqual(response.status_code, 403)

    def test_bearer_scheme_invalid_key_returns_403(self):
        response, _ = self._call_bad_key(f'Bearer badkey')
        self.assertEqual(response.status_code, 403)

    def test_unknown_scheme_passes_through_to_view(self):
        # Unknown scheme falls through without setting user — view proceeds but user is unset
        # (existing behaviour: only key/bearer set request.user; other schemes pass through)
        view = _make_view()
        request = _make_request('Basic dXNlcjpwYXNz')
        response = view(request)
        self.assertEqual(response.status_code, 200)

    def test_api_auth_is_csrf_exempt(self):
        # api_auth-decorated views must be CSRF-exempt so that external API clients
        # using Bearer/key auth can POST without providing a CSRF token.
        view = _make_view()
        self.assertTrue(
            getattr(view, 'csrf_exempt', False),
            "api_auth-decorated views should have csrf_exempt=True so POST requests "
            "from external services (e.g. migration scripts) are not rejected by "
            "Django's CSRF middleware.",
        )


class EnvVarUserScopeTest(SimpleTestCase):
    """Unit tests for EnvVarUser.has_scope() and scope parsing."""

    def _make_user(self, scopes=None):
        from .envvars import EnvVarUser
        return EnvVarUser(system='testsystem:test', apikey='testkey', scopes=scopes)

    # --- New estate-vocabulary scope names ---

    def test_user_with_eolas_write_scope_has_eolas_write(self):
        user = self._make_user(scopes=['eolas:write'])
        self.assertTrue(user.has_scope('eolas:write'))

    def test_user_with_eolas_read_scope_has_eolas_read(self):
        user = self._make_user(scopes=['eolas:read'])
        self.assertTrue(user.has_scope('eolas:read'))

    def test_user_with_eolas_read_does_not_have_eolas_write(self):
        user = self._make_user(scopes=['eolas:read'])
        self.assertFalse(user.has_scope('eolas:write'))

    # --- Pre-existing behaviour (kept for regression coverage) ---

    def test_user_with_write_scope_has_write(self):
        user = self._make_user(scopes=['write'])
        self.assertTrue(user.has_scope('write'))

    def test_user_with_read_scope_does_not_have_write(self):
        user = self._make_user(scopes=['read'])
        self.assertFalse(user.has_scope('write'))

    def test_user_with_no_scopes_has_no_permissions(self):
        user = self._make_user()
        self.assertFalse(user.has_scope('read'))
        self.assertFalse(user.has_scope('write'))
        self.assertFalse(user.has_scope('eolas:read'))
        self.assertFalse(user.has_scope('eolas:write'))

    def test_user_with_read_and_write_scopes_has_both(self):
        user = self._make_user(scopes=['read', 'write'])
        self.assertTrue(user.has_scope('read'))
        self.assertTrue(user.has_scope('write'))
        self.assertFalse(user.has_scope('admin'))

    def test_user_with_empty_scopes_list_has_no_permissions(self):
        user = self._make_user(scopes=[])
        self.assertFalse(user.has_scope('write'))
        self.assertFalse(user.has_scope('eolas:write'))


class ApiAuthScopeEnforcementTest(SimpleTestCase):
    """Tests for scope enforcement via @api_auth(required_scope=...)."""

    def _make_scoped_view(self, required_scope):
        """Return a view decorated with @api_auth(required_scope=...)."""
        @api_auth(required_scope=required_scope)
        def view(request):
            return HttpResponse(status=200)
        return view

    def _make_user_with_scopes(self, scopes):
        from .envvars import EnvVarUser
        return EnvVarUser(system='testsystem:test', apikey='testkey', scopes=scopes)

    def _call_scoped(self, user, required_scope='eolas:write'):
        view = self._make_scoped_view(required_scope)
        request = _make_request(f'Bearer testkey')
        with patch('lucos_eolas.lucosauth.decorators.getUserByKey', return_value=user):
            return view(request)

    # --- New estate-vocabulary scope names ---

    def test_eolas_write_scope_required_key_has_eolas_write_returns_200(self):
        user = self._make_user_with_scopes(['eolas:write'])
        response = self._call_scoped(user, required_scope='eolas:write')
        self.assertEqual(response.status_code, 200)

    def test_eolas_write_scope_required_key_has_no_scope_returns_403(self):
        user = self._make_user_with_scopes([])
        response = self._call_scoped(user, required_scope='eolas:write')
        self.assertEqual(response.status_code, 403)

    def test_eolas_write_scope_required_key_has_only_eolas_read_returns_403(self):
        user = self._make_user_with_scopes(['eolas:read'])
        response = self._call_scoped(user, required_scope='eolas:write')
        self.assertEqual(response.status_code, 403)

    def test_eolas_read_scope_required_key_has_eolas_read_returns_200(self):
        user = self._make_user_with_scopes(['eolas:read'])
        response = self._call_scoped(user, required_scope='eolas:read')
        self.assertEqual(response.status_code, 200)

    def test_eolas_read_scope_required_key_has_no_scope_returns_403(self):
        user = self._make_user_with_scopes([])
        response = self._call_scoped(user, required_scope='eolas:read')
        self.assertEqual(response.status_code, 403)

    # --- Pre-existing behaviour (kept for regression coverage) ---

    def test_write_scope_required_key_has_write_returns_200(self):
        user = self._make_user_with_scopes(['write'])
        response = self._call_scoped(user, required_scope='write')
        self.assertEqual(response.status_code, 200)

    def test_write_scope_required_key_has_read_and_write_returns_200(self):
        user = self._make_user_with_scopes(['read', 'write'])
        response = self._call_scoped(user, required_scope='write')
        self.assertEqual(response.status_code, 200)

    def test_write_scope_required_key_has_no_scope_returns_403(self):
        user = self._make_user_with_scopes([])
        response = self._call_scoped(user, required_scope='write')
        self.assertEqual(response.status_code, 403)

    def test_write_scope_required_key_has_only_read_scope_returns_403(self):
        user = self._make_user_with_scopes(['read'])
        response = self._call_scoped(user, required_scope='write')
        self.assertEqual(response.status_code, 403)

    def test_no_required_scope_key_with_no_scopes_returns_200(self):
        # @api_auth (no required_scope) — any valid key succeeds regardless of scopes
        user = self._make_user_with_scopes([])
        view = _make_view()
        request = _make_request('Bearer testkey')
        with patch('lucos_eolas.lucosauth.decorators.getUserByKey', return_value=user):
            response = view(request)
        self.assertEqual(response.status_code, 200)

    def test_scoped_view_is_csrf_exempt(self):
        # @api_auth(required_scope=...) views must also be CSRF-exempt
        view = self._make_scoped_view(required_scope='write')
        self.assertTrue(
            getattr(view, 'csrf_exempt', False),
            "@api_auth(required_scope=...) views should be CSRF-exempt.",
        )

    def test_scoped_view_invalid_key_returns_403(self):
        view = self._make_scoped_view(required_scope='write')
        request = _make_request('Bearer badkey')
        with patch('lucos_eolas.lucosauth.decorators.getUserByKey', return_value=None):
            response = view(request)
        self.assertEqual(response.status_code, 403)

    def test_scoped_view_no_auth_header_returns_401(self):
        view = self._make_scoped_view(required_scope='write')
        request = _make_request()
        response = view(request)
        self.assertEqual(response.status_code, 401)


# ---------------------------------------------------------------------------
# _LKGJWKSClient — reachability tracking (lucas42/lucos_eolas#333)
# ---------------------------------------------------------------------------

class LKGJWKSClientReachabilityTest(SimpleTestCase):
    """_LKGJWKSClient tracks whether the most recent fetch attempt hit a
    network error, independent of whether a last-known-good key let
    verification succeed anyway.
    """

    def setUp(self):
        from .aithne import _LKGJWKSClient, PyJWKClientNetworkError, PyJWKClientError
        self.error_cls = PyJWKClientNetworkError
        self.base_error_cls = PyJWKClientError
        self.client = _LKGJWKSClient.__new__(_LKGJWKSClient)
        self.client._client = MagicMock()
        self.client._last_good_key = None
        self.client._unreachable = False
        import threading
        self.client._lock = threading.Lock()

    def test_starts_reachable(self):
        self.assertFalse(self.client.is_unreachable())

    def test_network_error_class_is_not_the_broad_base_class(self):
        """Regression guard for the compat shim: PyJWKClientNetworkError must
        resolve to PyJWT's connection-specific exception (PyJWKClientConnectionError,
        added 2.8.0), not silently alias the broad PyJWKClientError base class —
        otherwise unrelated errors like "kid not found" get miscategorised as
        an aithne outage."""
        self.assertIsNot(self.error_cls, self.base_error_cls)

    def test_cold_start_network_error_marks_unreachable(self):
        """No cached key + network error: fails closed AND marks unreachable."""
        self.client._client.get_signing_key_from_jwt.side_effect = self.error_cls("boom")
        with self.assertRaises(self.error_cls):
            self.client.get_signing_key_from_jwt('token')
        self.assertTrue(self.client.is_unreachable())

    def test_network_error_with_cached_key_still_marks_unreachable(self):
        """Even when a last-known-good key masks the failure from the caller,
        the reachability signal must still flip — aithne's login page is down
        regardless of whether an existing session can still verify."""
        cached_key = MagicMock()
        self.client._last_good_key = cached_key
        self.client._client.get_signing_key_from_jwt.side_effect = self.error_cls("boom")
        result = self.client.get_signing_key_from_jwt('token')
        self.assertEqual(result, cached_key)
        self.assertTrue(self.client.is_unreachable())

    def test_successful_fetch_clears_unreachable(self):
        """A successful fetch (fresh or from the underlying client's own cache)
        self-heals the reachability signal — no separate recovery step needed."""
        self.client._unreachable = True
        self.client._client.get_signing_key_from_jwt.return_value = 'a-key'
        result = self.client.get_signing_key_from_jwt('token')
        self.assertEqual(result, 'a-key')
        self.assertFalse(self.client.is_unreachable())

    def test_kid_not_found_error_does_not_mark_unreachable(self):
        """A bare PyJWKClientError (e.g. "kid not found" after a successful
        JWKS refresh) means the endpoint WAS reached — it must propagate
        without flipping the reachability signal."""
        self.client._client.get_signing_key_from_jwt.side_effect = self.base_error_cls(
            'Unable to find a signing key that matches: "some-kid"'
        )
        with self.assertRaises(self.base_error_cls):
            self.client.get_signing_key_from_jwt('token')
        self.assertFalse(self.client.is_unreachable())


class IsAithneReachableTest(SimpleTestCase):
    """is_aithne_reachable() reflects the shared JWKS client's state."""

    def test_reflects_jwks_client_unreachable(self):
        import lucos_eolas.lucosauth.aithne as aithne_mod
        mock_client = MagicMock()
        mock_client.is_unreachable.return_value = True
        with patch.object(aithne_mod, '_jwks_client', mock_client):
            self.assertFalse(aithne_mod.is_aithne_reachable())

    def test_reflects_jwks_client_reachable(self):
        import lucos_eolas.lucosauth.aithne as aithne_mod
        mock_client = MagicMock()
        mock_client.is_unreachable.return_value = False
        with patch.object(aithne_mod, '_jwks_client', mock_client):
            self.assertTrue(aithne_mod.is_aithne_reachable())


# ---------------------------------------------------------------------------
# require_scope branch 3 — local page vs redirect when aithne is unreachable
# ---------------------------------------------------------------------------

class RequireScopeAithneUnavailableTest(SimpleTestCase):
    """Branch 3 renders a local page instead of redirecting when aithne is
    known to be unreachable (lucas42/lucos_eolas#333)."""

    def setUp(self):
        self.factory = RequestFactory()

    def _make_protected_view(self, scope='eolas:admin'):
        @require_scope(scope)
        def view(request):
            return HttpResponse(status=200)
        return view

    def _make_unauth_request(self, path='/admin/'):
        request = self.factory.get(path)
        request.user = AnonymousUser()
        request.aithne_scopes = []
        return request

    def test_renders_local_page_when_unreachable(self):
        # is_aithne_reachable is imported at module level into decorators.py
        # (`from .aithne import ... is_aithne_reachable`), so the name to
        # patch is the binding in the *consuming* module, not the source.
        view = self._make_protected_view()
        request = self._make_unauth_request()
        with patch('lucos_eolas.lucosauth.decorators.is_aithne_reachable', return_value=False):
            response = view(request)
        self.assertEqual(response.status_code, 503)
        self.assertIn(b'temporarily unavailable', response.content.lower())

    def test_does_not_redirect_when_unreachable(self):
        view = self._make_protected_view()
        request = self._make_unauth_request()
        with patch('lucos_eolas.lucosauth.decorators.is_aithne_reachable', return_value=False):
            response = view(request)
        self.assertNotEqual(response.status_code, 302)

    def test_still_redirects_when_reachable(self):
        """Existing behaviour is preserved when aithne is up."""
        view = self._make_protected_view()
        request = self._make_unauth_request()
        with patch('lucos_eolas.lucosauth.decorators.is_aithne_reachable', return_value=True), \
             patch.dict('os.environ', {'AITHNE_ORIGIN': 'http://aithne.test'}):
            response = view(request)
        self.assertEqual(response.status_code, 302)
        self.assertIn('/auth/login', response['Location'])
