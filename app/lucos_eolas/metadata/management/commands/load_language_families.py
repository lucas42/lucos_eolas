import requests
from django.core.management.base import BaseCommand
from django.db import transaction
from lucos_eolas.metadata.models import LanguageFamily

HEADERS = {"Accept": "application/ld+json"}
ROOT_URI = "https://id.loc.gov/vocabulary/iso639-5.jsonld"


class Command(BaseCommand):
	help = "Load all ISO 639-5 language families from LoC recursively, including all subfamilies."

	def handle(self, *args, **options):
		self._process_isolates()
		self.stdout.write("Fetching top-level ISO 639-5 families...")
		resp = requests.get(ROOT_URI, headers=HEADERS, allow_redirects=True)
		resp.raise_for_status()
		root_data = resp.json()  # LoC JSON-LD root is a list

		# Recursively import each top-level family
		with transaction.atomic():
			for term in root_data:
				uri = term.get('@id')
				if uri and uri.startswith("http://id.loc.gov/vocabulary/iso639-5/") :
					self._process_family(uri, None)

		self.stdout.write(self.style.SUCCESS("✅ Done importing ISO 639-5 families."))

	def _process_family(self, uri, parent):
		# Fetch JSON-LD for this family
		resp = requests.get(uri, headers=HEADERS, allow_redirects=True)
		resp.raise_for_status()
		data = resp.json()  # flat array of objects

		# Find the object in the array whose @id matches the URI
		family_entry = next((item for item in data if item.get('@id') == uri), None)
		if not family_entry:
			self.stdout.write(self.style.WARNING(f"No matching entry for {uri}"))
			return

		code = uri.rstrip('/').split('/')[-1]
		name_list = family_entry.get('http://www.w3.org/2004/02/skos/core#prefLabel', [])
		name = name_list[0].get('@value', 'Unknown') if name_list else 'Unknown'

		# Insert/update Django model
		obj, created = LanguageFamily.objects.update_or_create(
			code=code,
			defaults={"name": name, "parent": parent},
		)
		action = "Created" if created else "Updated"
		self.stdout.write(f"{action}: {code} → {name}")

		# Recursively process narrower concepts
		narrower_list = family_entry.get('http://www.w3.org/2004/02/skos/core#narrower', [])
		for child in narrower_list:
			child_uri = child.get('@id')
			if child_uri and child_uri.startswith("http://id.loc.gov/vocabulary/iso639-5/"):
				self._process_family(child_uri, obj)

	# Create a pseudo family to hold language isolates
	# NB: this isn't included in ISO 639-5, so the code here is invented
	def _process_isolates(self):
		obj, created = LanguageFamily.objects.update_or_create(
			code="qli", # Codes qaa-qtz are reserved for local use, so this won't clash with a future ISO 639 Code
			defaults={"name": "language isolates"},
		)
		action = "Created" if created else "Updated"
		self.stdout.write(f"{action}: language isolates")