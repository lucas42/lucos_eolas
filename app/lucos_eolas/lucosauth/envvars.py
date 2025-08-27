import os
from django.contrib.auth.models import AnonymousUser

class EnvVarUser(AnonymousUser):
	username = None
	USERNAME_FIELD = 'system'
	REQUIRED_FIELDS = []
	def __init__(self, system, apikey):
		super().__init__()
		self.system = system
		self.apikey = apikey
	def is_authenticated(self):
		return True
	def is_staff(self):
		return False
	def has_module_perms(self, app_label):
		if (app_label == 'metadata'):
			return True
		return False
	def has_perm(self, perm, obj=None):
		if (perm.startswith('metadata.')):
			return True
		return False
	def get_short_name(self):
		return self.system
	def get_long_name(self):
		return self.system

if "CLIENT_KEYS" not in os.environ:
	raise Exception("No CLIENT_KEYS environment variable specified")
usersByKey = {}
rawkeys = os.environ["CLIENT_KEYS"]
if rawkeys:
	pairs = rawkeys.split(";")
	for rawpair in pairs:
		pair = rawpair.split("=",2)
		system = pair[0].strip()
		apikey = pair[1].strip()
		user = EnvVarUser(system, apikey)
		usersByKey[apikey] = user

def getUserByKey(apikey):
	try:
		return usersByKey[apikey]
	except KeyError:
		return None
