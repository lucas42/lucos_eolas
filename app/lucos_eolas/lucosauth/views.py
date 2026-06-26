from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme, urlencode
import os


def loginview(request):
	"""Redirect to aithne login (ADR-0002 §5).

	The aithne_session cookie is set domain-wide by aithne after authentication,
	so on return AithneAuthMiddleware picks it up automatically — no ?token=
	handling or login() call needed.

	The ?next= value is derived from the server-side request path (never from a
	user-supplied query parameter) and validated as an internal path only, to
	prevent open-redirect abuse.
	"""
	aithne_origin = os.environ.get("AITHNE_ORIGIN", "https://aithne.l42.eu")

	# Use ?next= from query string if safe; otherwise default to /
	next_url = request.GET.get("next", "/")
	if not url_has_allowed_host_and_scheme(url=next_url, allowed_hosts={request.get_host()}):
		next_url = "/"

	login_url = f"{aithne_origin}/auth/login?{urlencode({'next': next_url})}"
	return redirect(login_url)
