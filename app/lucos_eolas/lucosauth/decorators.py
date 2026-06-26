from functools import wraps
import logging

from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

from .envvars import getUserByKey
from .aithne import aithne_login_redirect

logger = logging.getLogger(__name__)


def api_auth(func=None, *, required_scope=None):
	"""Decorator that enforces Bearer/key authentication on a view.

	Usage:
	  @api_auth                         — any valid key is accepted
	  @api_auth(required_scope='write') — key must have the 'write' scope

	When required_scope is set, an authenticated key that lacks that scope
	receives a 403.  A key with no scopes is always fail-closed for scoped
	endpoints.
	"""
	def decorator(f):
		@csrf_exempt
		@wraps(f)
		def _decorator(request, *args, **kwargs):
			if 'HTTP_AUTHORIZATION' not in request.META:
				return HttpResponse(status=401)
			try:
				authmeth, auth = request.META['HTTP_AUTHORIZATION'].split(' ', 1)
			except ValueError:
				return HttpResponse(status=400)
			if authmeth.lower() in ('key', 'bearer'):
				user = getUserByKey(apikey=auth)
				if user:
					request.user = user
					if required_scope and not user.has_scope(required_scope):
						return HttpResponse(status=403)
				else:
					return HttpResponse(status=403)
			return f(request, *args, **kwargs)
		return _decorator
	# Support both @api_auth and @api_auth(required_scope='...')
	if func is not None:
		return decorator(func)
	return decorator


def require_scope(scope):
	"""Decorator that enforces aithne JWT authentication and scope on a view.

	Three-branch pattern (ADR-0002 §4):
	  1. Valid token AND the required scope → proceed.
	  2. Valid token, scope missing → styled 403 naming the missing scope.
	     (Not a redirect — the user is already signed in; re-login yields the
	     same scopeless token, which would create an infinite loop.)
	  3. No valid token → redirect to aithne login with a ?next= full URL
	     pointing at the current page.

	request.aithne_scopes and request.user are populated by AithneAuthMiddleware
	before this decorator runs.
	"""
	def decorator(f):
		@wraps(f)
		def _decorator(request, *args, **kwargs):
			scopes = getattr(request, 'aithne_scopes', [])
			user = request.user

			# Branch 1: valid token + required scope → proceed
			if user.is_authenticated and scope in scopes:
				return f(request, *args, **kwargs)

			# Branch 2: valid token but scope missing → styled 403
			if user.is_authenticated:
				logger.warning(
					"Access denied to %s: scope '%s' required but not in %s",
					request.path, scope, scopes,
				)
				return HttpResponse(
					f"<html><head><title>Access Denied</title></head><body>"
					f"<p>You don't have access to this page. "
					f"Required scope: <code>{scope}</code></p>"
					f"<nav><a href='/'>&lt;- Home</a></nav></body></html>",
					status=403,
					content_type="text/html",
				)

			# Branch 3: no valid token → redirect to aithne login
			logger.warning(
				"Unauthenticated request to %s — no valid aithne token, redirecting to login",
				request.path,
			)
			return aithne_login_redirect(request)

		return _decorator
	return decorator
