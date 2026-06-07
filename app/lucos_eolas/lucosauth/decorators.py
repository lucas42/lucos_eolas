from functools import wraps
from .envvars import getUserByKey
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

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