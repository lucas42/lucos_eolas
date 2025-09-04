from functools import wraps
from .envvars import getUserByKey
from django.http import HttpResponse

def api_auth(func):
	@wraps(func)
	def _decorator(request, *args, **kwargs):
		if 'HTTP_AUTHORIZATION' in request.META:
			try:
				authmeth, auth = request.META['HTTP_AUTHORIZATION'].split(' ', 1)
			except ValueError:
				return HttpResponse(status=400)
			if authmeth.lower() == 'key':
				user = getUserByKey(apikey=auth)
				if user:
					request.user = user
				else:
					return HttpResponse(status=403)
		return func(request, *args, **kwargs)
	return _decorator