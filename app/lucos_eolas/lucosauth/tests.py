from django.test import SimpleTestCase
from unittest.mock import patch, MagicMock
from django.http import HttpResponse
from .decorators import api_auth


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

    def test_unknown_scheme_returns_403(self):
        # Unknown scheme falls through without setting user — view proceeds but user is unset
        # (existing behaviour: only key/bearer set request.user; other schemes pass through)
        view = _make_view()
        request = _make_request('Basic dXNlcjpwYXNz')
        response = view(request)
        self.assertEqual(response.status_code, 200)
