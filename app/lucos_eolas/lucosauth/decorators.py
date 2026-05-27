from functools import wraps
from .envvars import getUserByKey
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt

def api_auth(func):
	@csrf_exempt
	@wraps(func)
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
			else:
				return HttpResponse(status=403)
		return func(request, *args, **kwargs)
	return _decorator