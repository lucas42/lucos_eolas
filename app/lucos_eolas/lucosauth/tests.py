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
