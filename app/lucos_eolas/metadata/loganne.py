import requests
import os

def loganneRequest(data):
	data["source"] = "lucos_eolas"
	if not os.environ.get("LOGANNE_ENDPOINT"):
		return
	try:
		loganne_reponse = requests.post(os.environ.get("LOGANNE_ENDPOINT"), json=data);
		loganne_reponse.raise_for_status()
	except Exception as error:
		print("Error from Loganne: {}".format(error))
