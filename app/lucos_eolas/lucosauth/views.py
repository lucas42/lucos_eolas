import logging

from django.utils.http import url_has_allowed_host_and_scheme

from .aithne import aithne_login_redirect

logger = logging.getLogger(__name__)


def loginview(request):
	"""Redirect to aithne login (ADR-0002 §5).

	The aithne_session cookie is set domain-wide by aithne after authentication;
	AithneAuthMiddleware picks it up automatically on return — no ?token= handling
	or login() call needed.

	?next= from the incoming query string is validated as an internal path, then
	forwarded as a full URL so aithne knows which origin to redirect back to.
	"""
	next_path = request.GET.get("next", "/")
	if not url_has_allowed_host_and_scheme(url=next_path, allowed_hosts={request.get_host()}):
		logger.debug("loginview: rejecting external ?next=%s, falling back to /", next_path)
		next_path = "/"
	return aithne_login_redirect(request, next_path)
