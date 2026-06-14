from django.test import SimpleTestCase, RequestFactory
from unittest.mock import patch, MagicMock
from django.http import HttpResponse
from .decorators import api_auth
from .views import loginview


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


class LoginViewNextRedirectTest(SimpleTestCase):
    """Tests for the 'next' parameter validation in loginview."""

    def setUp(self):
        self.factory = RequestFactory()
        self.staff_user = MagicMock()
        self.staff_user.is_staff = True
        self.regular_user = MagicMock()
        self.regular_user.is_staff = False

    def _call_loginview(self, url, user, token='valid-token'):
        request = self.factory.get(url)
        with patch('lucos_eolas.lucosauth.views.authenticate', return_value=user), \
             patch('lucos_eolas.lucosauth.views.login'):
            return loginview(request)

    def test_same_origin_next_redirects(self):
        """A same-origin relative path in 'next' is followed after login."""
        response = self._call_loginview('/login?token=t&next=/some/page/', self.staff_user)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/some/page/')

    def test_external_next_redirects_to_root(self):
        """An external URL in 'next' is rejected; user is redirected to /."""
        response = self._call_loginview('/login?token=t&next=https://evil.example.com/', self.staff_user)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/')

    def test_no_next_redirects_to_root(self):
        """When 'next' is absent, user is redirected to /."""
        response = self._call_loginview('/login?token=t', self.staff_user)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/')

    def test_admin_next_non_staff_returns_403(self):
        """A non-staff user with next=/admin/... gets a 403."""
        response = self._call_loginview('/login?token=t&next=/admin/metadata/', self.regular_user)
        self.assertEqual(response.status_code, 403)

    def test_admin_next_staff_user_redirects(self):
        """A staff user with next=/admin/... is redirected normally."""
        response = self._call_loginview('/login?token=t&next=/admin/metadata/', self.staff_user)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/admin/metadata/')

    def test_external_next_with_admin_path_redirects_to_root(self):
        """An external URL that contains /admin/ in the path is still rejected."""
        response = self._call_loginview(
            '/login?token=t&next=https://evil.example.com/admin/',
            self.staff_user,
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response['Location'], '/')


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

    # --- Legacy alias support (dual-accept during migration) ---

    def test_legacy_write_accepted_for_eolas_write(self):
        """During migration, a key with legacy 'write' scope satisfies 'eolas:write' requirement."""
        user = self._make_user(scopes=['write'])
        self.assertTrue(user.has_scope('eolas:write'))

    def test_legacy_read_accepted_for_eolas_read(self):
        """During migration, a key with legacy 'read' scope satisfies 'eolas:read' requirement."""
        user = self._make_user(scopes=['read'])
        self.assertTrue(user.has_scope('eolas:read'))

    def test_legacy_read_does_not_satisfy_eolas_write(self):
        """Legacy 'read' must not grant 'eolas:write'."""
        user = self._make_user(scopes=['read'])
        self.assertFalse(user.has_scope('eolas:write'))

    def test_legacy_write_does_not_satisfy_eolas_read(self):
        """Legacy 'write' must not grant 'eolas:read'."""
        user = self._make_user(scopes=['write'])
        self.assertFalse(user.has_scope('eolas:read'))

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

    def test_eolas_write_scope_required_legacy_write_returns_200(self):
        """During migration: key with legacy 'write' satisfies eolas:write requirement."""
        user = self._make_user_with_scopes(['write'])
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

    def test_eolas_read_scope_required_legacy_read_returns_200(self):
        """During migration: key with legacy 'read' satisfies eolas:read requirement."""
        user = self._make_user_with_scopes(['read'])
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
