from django.db import models
from django import utils
from django.contrib.auth.backends import BaseBackend
from django.contrib.auth.models import User
import json, urllib.request, urllib.error, os

if "AUTH_ORIGIN" not in os.environ:
	raise Exception("No AUTH_ORIGIN environment variable specified")

class LucosAuthBackend(BaseBackend):
	def authenticate(self, request, token):
		print("LucosAuthBackend token:"+str(token))
		url = os.environ["AUTH_ORIGIN"]+'/data?' + utils.http.urlencode({'token': token})
		try:
			data = json.load(urllib.request.urlopen(url, timeout=5))
		except urllib.error.HTTPError:
			return None
		except urllib.error.URLError as e:
			print("Error fetching data from auth service: "+e.message+" "+url)
			return None
		if (data['id'] == None):
			print("No id returned by auth service; "+url)
			return None
			print("Don't recognise that user id "+data['id'])
			return None
		(user, created) = User.objects.get_or_create(id=data["id"])
		if created:
			print("Created auth user for id "+str(data["id"]))
			user.username = data["name"]
			# Permission models are complicated.  While there's only one user of the system, make that known ID a superuser
			if (data['id'] == "2"):
				user.is_staff = True
				user.is_superuser = True
				print("User "+str(user.id)+" has been given superuser permissions")
			user.save()
		return user

	def get_user(self, user_id):
		try:
			user = User.objects.get(pk=user_id)
			return user
		except User.DoesNotExist:
			return None
