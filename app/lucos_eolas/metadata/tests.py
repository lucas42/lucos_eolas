import json
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.contrib.auth.models import User
from django.http import QueryDict
from unittest.mock import patch, MagicMock, call
from django.core.exceptions import ValidationError
from .checks import (
    get_place_consistency_checks, get_wikipedia_slug_check, _check_no_invalid_wikipedia_slugs,
    UNIVERSE_PLACE_ID, refresh_check_cache, get_cached_checks, CHECKS_CACHE_KEY,
)
from .fields import ArrayWidget
from .models import DayOfWeek, Calendar, Month, HistoricalEvent, Festival, FestivalPeriod, Language, LanguageFamily, TransportMode, Vehicle, Person, CreativeWork, CreativeWorkType, PlaceType
from .utils_case import smart_lower, smart_title
from .views import _safe_local_redirect


# ─── HTTP Endpoint Tests ───────────────────────────────────────────────────────

class InfoEndpointTest(TestCase):
	"""/_info endpoint returns correct JSON structure."""

	def test_returns_200(self):
		response = self.client.get('/_info')
		self.assertEqual(response.status_code, 200)

	def test_returns_expected_fields(self):
		response = self.client.get('/_info')
		data = response.json()
		self.assertEqual(data['system'], 'lucos_eolas')
		self.assertIn('checks', data)
		self.assertIn('ci', data)


class InfoEndpointCacheTest(TestCase):
	"""/_info reads from cache and returns pending placeholders on cold start."""

	def setUp(self):
		cache.clear()

	def tearDown(self):
		cache.clear()

	def test_cold_cache_returns_pending_for_all_checks(self):
		"""When cache is empty, /_info returns a pending placeholder for each check."""
		response = self.client.get('/_info')
		self.assertEqual(response.status_code, 200)
		data = response.json()
		for check_name in [
			'no-circular-containment',
			'no-real-place-in-fictional',
			'places-in-universe',
			'no-invalid-wikipedia-slugs',
		]:
			self.assertIn(check_name, data['checks'])
			check = data['checks'][check_name]
			self.assertFalse(check['ok'])
			self.assertIn('pending', check['techDetail'].lower())
			self.assertIn('failThreshold', check)

	@patch('lucos_eolas.metadata.views.get_cached_checks')
	def test_warm_cache_returns_cached_results(self, mock_get_cached):
		"""When cache is populated, /_info returns the cached check results."""
		fake_checks = {
			'no-circular-containment': {'ok': True, 'techDetail': 'No cycles found'},
			'no-real-place-in-fictional': {'ok': True, 'techDetail': 'All good'},
			'places-in-universe': {'ok': False, 'techDetail': 'BFS check', 'debug': 'Orphan found'},
			'no-invalid-wikipedia-slugs': {'ok': True, 'techDetail': 'All valid'},
		}
		mock_get_cached.return_value = fake_checks
		response = self.client.get('/_info')
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertEqual(data['checks'], fake_checks)


class RefreshCheckCacheTest(TestCase):
	"""refresh_check_cache() populates the Django cache; get_cached_checks() reads it."""

	def setUp(self):
		cache.clear()

	def tearDown(self):
		cache.clear()

	@patch('lucos_eolas.metadata.checks.get_place_consistency_checks')
	@patch('lucos_eolas.metadata.checks.get_wikipedia_slug_check')
	def test_refresh_stores_all_checks(self, mock_wiki, mock_place):
		"""refresh_check_cache() merges place and slug checks and stores them."""
		mock_place.return_value = {
			'no-circular-containment': {'ok': True, 'techDetail': 'ok'},
			'no-real-place-in-fictional': {'ok': True, 'techDetail': 'ok'},
			'places-in-universe': {'ok': True, 'techDetail': 'ok'},
		}
		mock_wiki.return_value = {'ok': True, 'techDetail': 'ok'}

		refresh_check_cache()

		cached = get_cached_checks()
		self.assertIsNotNone(cached)
		self.assertIn('no-circular-containment', cached)
		self.assertIn('no-real-place-in-fictional', cached)
		self.assertIn('places-in-universe', cached)
		self.assertIn('no-invalid-wikipedia-slugs', cached)
		self.assertTrue(cached['no-circular-containment']['ok'])
		self.assertTrue(cached['no-invalid-wikipedia-slugs']['ok'])

	@patch('lucos_eolas.metadata.checks.get_place_consistency_checks')
	@patch('lucos_eolas.metadata.checks.get_wikipedia_slug_check')
	def test_refresh_preserves_failing_checks(self, mock_wiki, mock_place):
		"""A failing check result is stored verbatim (not overridden to pass)."""
		mock_place.return_value = {
			'no-circular-containment': {'ok': False, 'techDetail': 'x', 'debug': 'cycle at A'},
			'no-real-place-in-fictional': {'ok': True, 'techDetail': 'ok'},
			'places-in-universe': {'ok': True, 'techDetail': 'ok'},
		}
		mock_wiki.return_value = {'ok': True, 'techDetail': 'ok'}

		refresh_check_cache()

		cached = get_cached_checks()
		self.assertFalse(cached['no-circular-containment']['ok'])
		self.assertEqual(cached['no-circular-containment']['debug'], 'cycle at A')

	def test_get_cached_checks_returns_none_before_refresh(self):
		"""get_cached_checks() returns None when nothing has been cached yet."""
		self.assertIsNone(get_cached_checks())

	@patch('lucos_eolas.metadata.checks.get_place_consistency_checks')
	@patch('lucos_eolas.metadata.checks.get_wikipedia_slug_check')
	def test_refresh_overwrites_previous_cache(self, mock_wiki, mock_place):
		"""A second refresh_check_cache() call replaces the previous cached value."""
		mock_place.return_value = {
			'no-circular-containment': {'ok': True, 'techDetail': 'ok'},
			'no-real-place-in-fictional': {'ok': True, 'techDetail': 'ok'},
			'places-in-universe': {'ok': True, 'techDetail': 'ok'},
		}
		mock_wiki.return_value = {'ok': True, 'techDetail': 'ok'}
		refresh_check_cache()

		mock_place.return_value = {
			'no-circular-containment': {'ok': False, 'techDetail': 'x', 'debug': 'cycle'},
			'no-real-place-in-fictional': {'ok': True, 'techDetail': 'ok'},
			'places-in-universe': {'ok': True, 'techDetail': 'ok'},
		}
		refresh_check_cache()

		cached = get_cached_checks()
		self.assertFalse(cached['no-circular-containment']['ok'])


class CategoriesJsonEndpointTest(SimpleTestCase):
	"""GET /metadata/categories.json — unauthenticated endpoint returning all category colours."""

	def test_returns_200_without_auth(self):
		response = self.client.get('/metadata/categories.json')
		self.assertEqual(response.status_code, 200)

	def test_returns_json(self):
		response = self.client.get('/metadata/categories.json')
		self.assertIn('application/json', response['Content-Type'])

	def test_returns_list(self):
		response = self.client.get('/metadata/categories.json')
		data = response.json()
		self.assertIsInstance(data, list)

	def test_has_all_seventeen_categories(self):
		response = self.client.get('/metadata/categories.json')
		data = response.json()
		self.assertEqual(len(data), 17)

	def test_each_entry_has_required_fields(self):
		response = self.client.get('/metadata/categories.json')
		data = response.json()
		for entry in data:
			self.assertIn('name', entry)
			self.assertIn('slug', entry)
			self.assertIn('background', entry)
			self.assertIn('border', entry)
			self.assertIn('text', entry)

	def test_no_null_colour_values(self):
		response = self.client.get('/metadata/categories.json')
		data = response.json()
		for entry in data:
			self.assertIsNotNone(entry['background'])
			self.assertIsNotNone(entry['border'])
			self.assertIsNotNone(entry['text'])

	def test_slug_is_lowercase_name(self):
		response = self.client.get('/metadata/categories.json')
		data = response.json()
		for entry in data:
			self.assertEqual(entry['slug'], entry['name'].lower())

	def test_known_category_has_correct_colours(self):
		"""Musical category should have the same colours as the search component hardcode."""
		response = self.client.get('/metadata/categories.json')
		data = response.json()
		musical = next(e for e in data if e['name'] == 'Musical')
		self.assertEqual(musical['background'], '#000060')
		self.assertEqual(musical['border'], '#000020')
		self.assertEqual(musical['text'], '#ffffff')

	def test_colours_are_hex_strings(self):
		"""All colour values should be CSS hex strings starting with #."""
		import re
		hex_pattern = re.compile(r'^#[0-9a-fA-F]{3,8}$')
		response = self.client.get('/metadata/categories.json')
		data = response.json()
		for entry in data:
			for field in ('background', 'border', 'text'):
				self.assertRegex(entry[field], hex_pattern, f"{entry['name']} {field} is not a valid hex colour")


class OntologyEndpointTest(SimpleTestCase):
	"""ontology endpoint returns RDF content without auth."""

	def test_returns_200(self):
		response = self.client.get('/ontology')
		self.assertEqual(response.status_code, 200)

	def test_returns_turtle_by_default(self):
		response = self.client.get('/ontology')
		self.assertIn('text/turtle', response['Content-Type'])

	def test_returns_json_ld_when_requested(self):
		response = self.client.get('/ontology', HTTP_ACCEPT='application/ld+json')
		self.assertIn('application/ld+json', response['Content-Type'])

	def test_ontology_includes_preferred_identifier(self):
		import rdflib
		response = self.client.get('/ontology')
		g = rdflib.Graph()
		g.parse(data=response.content, format='turtle')
		preferred_id_uri = next(
			(s for s in g.subjects() if str(s).endswith('/preferredIdentifier')),
			None,
		)
		self.assertIsNotNone(preferred_id_uri, "preferredIdentifier term not found in ontology")
		self.assertIn(
			(preferred_id_uri, rdflib.RDF.type, rdflib.OWL.ObjectProperty),
			g,
			"preferredIdentifier is not declared as owl:ObjectProperty",
		)


class ApiAuthDecoratorTest(TestCase):
	"""api_auth decorator enforces key authentication."""

	def test_no_auth_header_returns_401(self):
		response = self.client.get('/metadata/all/data/')
		self.assertEqual(response.status_code, 401)

	def test_invalid_key_returns_403(self):
		response = self.client.get('/metadata/all/data/', HTTP_AUTHORIZATION='key wrongkey')
		self.assertEqual(response.status_code, 403)

	def test_valid_key_returns_200(self):
		response = self.client.get('/metadata/all/data/', HTTP_AUTHORIZATION='key key')
		self.assertEqual(response.status_code, 200)

	def test_bearer_token_also_accepted(self):
		response = self.client.get('/metadata/all/data/', HTTP_AUTHORIZATION='bearer key')
		self.assertEqual(response.status_code, 200)


class TypeListEndpointTest(TestCase):
	"""type_list endpoint returns a JSON array of items for a given type."""

	AUTH = {'HTTP_AUTHORIZATION': 'key key'}

	def test_requires_auth(self):
		response = self.client.get('/metadata/dayofweek/list/')
		self.assertEqual(response.status_code, 401)

	def test_invalid_key_rejected(self):
		response = self.client.get('/metadata/dayofweek/list/', HTTP_AUTHORIZATION='key wrongkey')
		self.assertEqual(response.status_code, 403)

	def test_unknown_type_returns_404(self):
		response = self.client.get('/metadata/nonexistenttype/list/', **self.AUTH)
		self.assertEqual(response.status_code, 404)

	def test_returns_json_array(self):
		DayOfWeek.objects.create(name='Monday', order=1)
		response = self.client.get('/metadata/dayofweek/list/', **self.AUTH)
		self.assertEqual(response.status_code, 200)
		self.assertIn('application/json', response['Content-Type'])
		data = response.json()
		self.assertIsInstance(data, list)

	def test_empty_type_returns_empty_array(self):
		# No DayOfWeek objects in DB → empty list
		response = self.client.get('/metadata/dayofweek/list/', **self.AUTH)
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json(), [])

	def test_item_has_base_fields(self):
		day = DayOfWeek.objects.create(name='Tuesday', order=2)
		response = self.client.get('/metadata/dayofweek/list/', **self.AUTH)
		data = response.json()
		self.assertEqual(len(data), 1)
		item = data[0]
		self.assertEqual(item['id'], day.pk)
		self.assertIn('uri', item)
		self.assertIn('/metadata/dayofweek/', item['uri'])
		self.assertEqual(item['name'], 'Tuesday')

	def test_item_includes_type_specific_fields(self):
		# DayOfWeek has an 'order' field — it must appear in the JSON
		DayOfWeek.objects.create(name='Wednesday', order=3)
		response = self.client.get('/metadata/dayofweek/list/', **self.AUTH)
		item = response.json()[0]
		self.assertEqual(item['order'], 3)

	def test_item_includes_alternate_names_and_wikipedia_slug(self):
		# alternate_names and wikipedia_slug are real fields — they must be included
		DayOfWeek.objects.create(name='Thursday', order=4, wikipedia_slug='Thursday')
		response = self.client.get('/metadata/dayofweek/list/', **self.AUTH)
		item = response.json()[0]
		self.assertIn('alternate_names', item)
		self.assertIn('wikipedia_slug', item)
		self.assertEqual(item['wikipedia_slug'], 'Thursday')
		self.assertIsInstance(item['alternate_names'], list)

	def test_foreign_key_serialised_as_dict(self):
		# Month has a FK to Calendar — it should appear as {id, uri, name}
		calendar = Calendar.objects.create(name='Gregorian')
		Month.objects.create(name='January', calendar=calendar, order_in_calendar=1)
		response = self.client.get('/metadata/month/list/', **self.AUTH)
		self.assertEqual(response.status_code, 200)
		item = response.json()[0]
		self.assertIn('calendar', item)
		cal_data = item['calendar']
		self.assertEqual(cal_data['id'], calendar.pk)
		self.assertIn('uri', cal_data)
		self.assertEqual(cal_data['name'], 'Gregorian')

	def test_month_temporal_month_code_falls_back_to_order_in_calendar(self):
		# When temporal_month_code is not set, it should be derived from order_in_calendar
		calendar = Calendar.objects.create(name='Gregorian')
		Month.objects.create(name='September', calendar=calendar, order_in_calendar=9)
		response = self.client.get('/metadata/month/list/', **self.AUTH)
		item = response.json()[0]
		self.assertEqual(item['temporal_month_code'], 'M09')

	def test_month_temporal_month_code_uses_explicit_value_when_set(self):
		# When temporal_month_code is set explicitly (e.g. Hebrew months), it overrides the fallback
		calendar = Calendar.objects.create(name='Hebrew')
		# Nisan is month 1 in eolas (Nisan-first), but M07 in Temporal (Tishrei-first)
		Month.objects.create(name='Nisan', calendar=calendar, order_in_calendar=1, temporal_month_code='M07')
		response = self.client.get('/metadata/month/list/', **self.AUTH)
		item = response.json()[0]
		self.assertEqual(item['temporal_month_code'], 'M07')

	def test_multiple_items_all_returned(self):
		DayOfWeek.objects.create(name='Friday', order=5)
		DayOfWeek.objects.create(name='Saturday', order=6)
		DayOfWeek.objects.create(name='Sunday', order=7)
		response = self.client.get('/metadata/dayofweek/list/', **self.AUTH)
		self.assertEqual(len(response.json()), 3)


class AllRdfEndpointTest(TestCase):
	"""all_rdf endpoint returns valid RDF."""

	def test_returns_turtle_by_default(self):
		response = self.client.get('/metadata/all/data/', HTTP_AUTHORIZATION='key key')
		self.assertEqual(response.status_code, 200)
		self.assertIn('text/turtle', response['Content-Type'])

	def test_returns_json_ld_when_requested(self):
		response = self.client.get('/metadata/all/data/', HTTP_AUTHORIZATION='key key', HTTP_ACCEPT='application/ld+json')
		self.assertEqual(response.status_code, 200)
		self.assertIn('application/ld+json', response['Content-Type'])


class AllRdfPrefLabelRegressionTest(TestCase):
	"""Regression: ontology prefLabels for external-namespace parent classes appear in the bulk RDF export.

	These tests exercise the actual all_rdf() code path (ontology_graph() + instance loop)
	rather than get_rdf(include_type_label=True) directly, which was the gap exploited by #271
	(the fix landed in a branch never reached by the bulk export).
	"""

	AUTH = {'HTTP_AUTHORIZATION': 'key key'}

	def _parsed_graph(self):
		import rdflib
		response = self.client.get('/metadata/all/data/', **self.AUTH)
		self.assertEqual(response.status_code, 200)
		g = rdflib.Graph()
		g.parse(data=response.content, format='turtle')
		return g

	def test_bulk_export_contains_schema_place_preflabel(self):
		"""schema:Place skos:prefLabel 'Place'@en is present in the bulk RDF export."""
		import rdflib
		g = self._parsed_graph()
		self.assertIn(
			(rdflib.SDO.Place, rdflib.SKOS.prefLabel, rdflib.Literal("Place", lang="en")),
			g,
			"Expected English prefLabel for schema:Place in the bulk RDF export",
		)

	def test_bulk_export_contains_schema_creativework_preflabel(self):
		"""schema:CreativeWork skos:prefLabel 'Creative Work'@en is present in the bulk RDF export."""
		import rdflib
		g = self._parsed_graph()
		self.assertIn(
			(rdflib.SDO.CreativeWork, rdflib.SKOS.prefLabel, rdflib.Literal("Creative Work", lang="en")),
			g,
			"Expected English prefLabel for schema:CreativeWork in the bulk RDF export",
		)

	def test_bulk_export_contains_dbpedia_meanoftransportation_preflabel(self):
		"""dbpedia:MeanOfTransportation skos:prefLabel 'Means of Transport'@en is present in the bulk RDF export."""
		import rdflib
		DBPEDIA_NS = rdflib.Namespace("https://dbpedia.org/ontology/")
		g = self._parsed_graph()
		self.assertIn(
			(DBPEDIA_NS.MeanOfTransportation, rdflib.SKOS.prefLabel, rdflib.Literal("Means of Transport", lang="en")),
			g,
			"Expected English prefLabel for dbpedia:MeanOfTransportation in the bulk RDF export",
		)


class BatchNamesEndpointTest(TestCase):
	"""POST /metadata/names — batch URI to canonical name resolution."""

	AUTH = {'HTTP_AUTHORIZATION': 'key key'}

	def _post(self, body, auth=True, content_type='application/json'):
		headers = dict(self.AUTH) if auth else {}
		return self.client.post(
			'/metadata/names',
			data=json.dumps(body),
			content_type=content_type,
			**headers,
		)

	# ── Authentication ──────────────────────────────────────────────────────────

	def test_no_auth_returns_401(self):
		response = self._post([], auth=False)
		self.assertEqual(response.status_code, 401)

	def test_invalid_key_returns_403(self):
		response = self.client.post(
			'/metadata/names',
			data=json.dumps([]),
			content_type='application/json',
			HTTP_AUTHORIZATION='key wrongkey',
		)
		self.assertEqual(response.status_code, 403)

	# ── Method ──────────────────────────────────────────────────────────────────

	def test_get_returns_405(self):
		response = self.client.get('/metadata/names', **self.AUTH)
		self.assertEqual(response.status_code, 405)

	# ── Content-Type ────────────────────────────────────────────────────────────

	def test_wrong_content_type_returns_415(self):
		response = self._post([], content_type='text/plain')
		self.assertEqual(response.status_code, 415)

	def test_form_encoded_content_type_returns_415(self):
		response = self._post([], content_type='application/x-www-form-urlencoded')
		self.assertEqual(response.status_code, 415)

	# ── Input validation ─────────────────────────────────────────────────────────

	def test_invalid_json_returns_400(self):
		response = self.client.post(
			'/metadata/names',
			data=b'not-json',
			content_type='application/json',
			**self.AUTH,
		)
		self.assertEqual(response.status_code, 400)

	def test_non_array_body_returns_400(self):
		response = self._post({'uri': 'http://localhost/metadata/person/1/'})
		self.assertEqual(response.status_code, 400)

	# ── Successful resolution ────────────────────────────────────────────────────

	def test_empty_list_returns_empty_dict(self):
		response = self._post([])
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json(), {})

	def test_returns_json_content_type(self):
		response = self._post([])
		self.assertIn('application/json', response['Content-Type'])

	def test_resolves_known_uri(self):
		person = Person.objects.create(name='David Bowie')
		uri = person.get_absolute_url()
		response = self._post([uri])
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertEqual(data[uri], 'David Bowie')

	def test_resolves_multiple_uris_of_same_type(self):
		person1 = Person.objects.create(name='David Bowie')
		person2 = Person.objects.create(name='Paul McCartney')
		uri1, uri2 = person1.get_absolute_url(), person2.get_absolute_url()
		response = self._post([uri1, uri2])
		self.assertEqual(response.status_code, 200)
		data = response.json()
		self.assertEqual(data[uri1], 'David Bowie')
		self.assertEqual(data[uri2], 'Paul McCartney')

	def test_resolves_uris_of_different_types(self):
		person = Person.objects.create(name='Beethoven')
		calendar = Calendar.objects.create(name='Gregorian')
		uri_person = person.get_absolute_url()
		uri_cal = calendar.get_absolute_url()
		response = self._post([uri_person, uri_cal])
		data = response.json()
		self.assertEqual(data[uri_person], 'Beethoven')
		self.assertEqual(data[uri_cal], 'Gregorian')

	def test_unknown_uri_omitted(self):
		"""URIs with a valid structure but non-existent PK are omitted from the response."""
		unknown_uri = 'http://localhost/metadata/person/99999/'
		response = self._post([unknown_uri])
		self.assertEqual(response.status_code, 200)
		self.assertNotIn(unknown_uri, response.json())

	def test_malformed_uri_path_omitted(self):
		"""URIs with wrong path structure are silently omitted."""
		response = self._post(['not-a-valid-uri', 'http://localhost/wrong/path'])
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json(), {})

	def test_non_string_items_skipped(self):
		"""Non-string items in the list are skipped without error."""
		response = self._post([42, None, True])
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.json(), {})

	def test_mixed_found_and_not_found_uris(self):
		"""Only found URIs appear in the response; missing ones are silently omitted."""
		person = Person.objects.create(name='George Harrison')
		found_uri = person.get_absolute_url()
		missing_uri = 'http://localhost/metadata/person/99999/'
		response = self._post([found_uri, missing_uri])
		data = response.json()
		self.assertIn(found_uri, data)
		self.assertNotIn(missing_uri, data)
		self.assertEqual(data[found_uri], 'George Harrison')


class ContentNegotiationTest(SimpleTestCase):
	"""thing_entrypoint redirects to /data/ for RDF and /change/ for HTML."""

	def test_html_accept_redirects_to_change(self):
		response = self.client.get('/metadata/placetype/1/', HTTP_ACCEPT='text/html')
		self.assertEqual(response.status_code, 303)
		self.assertIn('/change/', response['Location'])

	def test_rdf_accept_redirects_to_data(self):
		response = self.client.get('/metadata/placetype/1/', HTTP_ACCEPT='text/turtle')
		self.assertEqual(response.status_code, 303)
		self.assertIn('/data/', response['Location'])

	def test_no_accept_header_redirects_to_change(self):
		response = self.client.get('/metadata/placetype/1/')
		self.assertEqual(response.status_code, 303)
		self.assertIn('/change/', response['Location'])


class SafeLocalRedirectTest(SimpleTestCase):
	"""_safe_local_redirect blocks external URLs and passes through relative paths."""

	def test_relative_path_unchanged(self):
		self.assertEqual(_safe_local_redirect('/metadata/placetype/1/data/'), '/metadata/placetype/1/data/')

	def test_https_url_redirects_to_root(self):
		self.assertEqual(_safe_local_redirect('https://evil.example.com/phish'), '/')

	def test_http_url_redirects_to_root(self):
		self.assertEqual(_safe_local_redirect('http://evil.example.com/'), '/')

	def test_protocol_relative_url_redirects_to_root(self):
		# //evil.example.com has no scheme but has a netloc
		self.assertEqual(_safe_local_redirect('//evil.example.com/phish'), '/')


# ─── Merge Action Tests ───────────────────────────────────────────────────────

@override_settings(AUTHENTICATION_BACKENDS=['django.contrib.auth.backends.ModelBackend'])
class MergeEntitiesActionTest(TestCase):
	"""merge_entities admin action fires Loganne events and deletes the source."""

	def setUp(self):
		user = User.objects.create_superuser('testadmin', 'admin@test.com', 'password')
		self.client.force_login(user, backend='django.contrib.auth.backends.ModelBackend')

	def _make_event(self, name):
		return HistoricalEvent.objects.create(name=name)

	@patch('lucos_eolas.metadata.admin.updateLoganne')
	def test_confirmation_page_shown_on_first_post(self, mock_loganne):
		source = self._make_event('Alpha')
		target = self._make_event('Beta')
		response = self.client.post(
			'/metadata/historicalevent/',
			{
				'action': 'merge_entities',
				'_selected_action': [str(source.pk), str(target.pk)],
			},
			follow=False,
		)
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Confirm merge')
		self.assertContains(response, 'Alpha')
		self.assertContains(response, 'Beta')
		mock_loganne.assert_not_called()

	@patch('lucos_eolas.metadata.admin.updateLoganne')
	def test_merge_deletes_source_and_fires_loganne(self, mock_loganne):
		source = self._make_event('Swearing')
		target = self._make_event('Profanity')
		source_url = source.get_absolute_url()
		target_url = target.get_absolute_url()

		self.client.post(
			'/metadata/historicalevent/',
			{
				'action': 'merge_entities',
				'_selected_action': [str(source.pk), str(target.pk)],
				'apply_merge': '1',
				'target_id': str(target.pk),
			},
		)

		self.assertFalse(HistoricalEvent.objects.filter(pk=source.pk).exists(), 'Source should be deleted')
		self.assertTrue(HistoricalEvent.objects.filter(pk=target.pk).exists(), 'Target should survive')
		item_type = HistoricalEvent._meta.verbose_name.title()
		mock_loganne.assert_called_once_with(
			type='itemMerged',
			humanReadable=f'{item_type} "Swearing" merged into "Profanity"',
			url=target_url,
			level='routine',
			sourceUri=source_url,
			targetUri=target_url,
			itemType=item_type,
		)

	@patch('lucos_eolas.metadata.admin.updateLoganne')
	def test_merge_does_not_fire_itemDeleted(self, mock_loganne):
		source = self._make_event('Old Name')
		target = self._make_event('New Name')
		self.client.post(
			'/metadata/historicalevent/',
			{
				'action': 'merge_entities',
				'_selected_action': [str(source.pk), str(target.pk)],
				'apply_merge': '1',
				'target_id': str(target.pk),
			},
		)
		called_types = [c.kwargs['type'] for c in mock_loganne.call_args_list]
		self.assertNotIn('itemDeleted', called_types, 'itemDeleted should not fire during a merge')

	@patch('lucos_eolas.metadata.admin.updateLoganne')
	def test_fewer_than_two_selected_shows_error(self, mock_loganne):
		entity = self._make_event('Solo')
		response = self.client.post(
			'/metadata/historicalevent/',
			{
				'action': 'merge_entities',
				'_selected_action': [str(entity.pk)],
			},
			follow=True,
		)
		self.assertContains(response, 'Select at least 2')
		mock_loganne.assert_not_called()


# ─── Existing Unit Tests ───────────────────────────────────────────────────────


def make_place(pk, name, fictional=False, contained_in_ids=None):
	"""Create a mock Place object."""
	place = MagicMock()
	place.pk = pk
	place.name = name
	place.fictional = fictional
	place.contained_in = MagicMock()
	place.contained_in.all.return_value = []
	return place


class PlaceConsistencyChecksTest(SimpleTestCase):

	def _run_checks(self, places, containment_map):
		"""
		Helper to run checks with controlled data.

		places: list of mock Place objects
		containment_map: dict of place_pk -> list of parent Place objects
		"""
		place_dict = {p.pk: p for p in places}
		for place in places:
			parent_pks = containment_map.get(place.pk, [])
			parents = [place_dict[pk] for pk in parent_pks]
			place.contained_in.all.return_value = parents

		mock_qs = MagicMock()
		mock_qs.__iter__ = lambda self: iter(places)
		mock_qs.all.return_value = places

		def fake_objects_all():
			return places

		def fake_prefetch_related_qs(places_list):
			qs = MagicMock()
			qs.__iter__ = lambda self: iter(places_list)
			return qs

		with patch('lucos_eolas.metadata.models.Place') as MockPlace:
			MockPlace.objects.all.return_value = places
			MockPlace.objects.prefetch_related.return_value = fake_prefetch_related_qs(places)
			return get_place_consistency_checks()

	# --- no-circular-containment ---

	def test_no_cycle_passes(self):
		universe = make_place(UNIVERSE_PLACE_ID, 'Universe')
		earth = make_place(1, 'Earth')
		london = make_place(2, 'London')
		# london -> earth -> universe
		checks = self._run_checks(
			[universe, earth, london],
			{earth.pk: [UNIVERSE_PLACE_ID], london.pk: [earth.pk]}
		)
		self.assertTrue(checks['no-circular-containment']['ok'])

	def test_cycle_detected(self):
		a = make_place(1, 'A')
		b = make_place(2, 'B')
		c = make_place(3, 'C')
		# A -> B -> C -> A
		checks = self._run_checks(
			[a, b, c],
			{a.pk: [b.pk], b.pk: [c.pk], c.pk: [a.pk]}
		)
		self.assertFalse(checks['no-circular-containment']['ok'])
		self.assertIn('debug', checks['no-circular-containment'])

	# --- no-real-place-in-fictional ---

	def test_real_place_in_real_parent_passes(self):
		universe = make_place(UNIVERSE_PLACE_ID, 'Universe')
		earth = make_place(1, 'Earth')
		london = make_place(2, 'London')
		checks = self._run_checks(
			[universe, earth, london],
			{earth.pk: [UNIVERSE_PLACE_ID], london.pk: [earth.pk]}
		)
		self.assertTrue(checks['no-real-place-in-fictional']['ok'])

	def test_fictional_place_in_fictional_parent_passes(self):
		universe = make_place(UNIVERSE_PLACE_ID, 'Universe')
		middle_earth = make_place(10, 'Middle-earth', fictional=True)
		shire = make_place(11, 'The Shire', fictional=True)
		checks = self._run_checks(
			[universe, middle_earth, shire],
			{shire.pk: [middle_earth.pk]}
		)
		self.assertTrue(checks['no-real-place-in-fictional']['ok'])

	def test_real_place_in_fictional_parent_fails(self):
		universe = make_place(UNIVERSE_PLACE_ID, 'Universe')
		fictional_country = make_place(10, 'Narnia', fictional=True)
		real_town = make_place(11, 'Oxford')
		checks = self._run_checks(
			[universe, fictional_country, real_town],
			{real_town.pk: [fictional_country.pk]}
		)
		self.assertFalse(checks['no-real-place-in-fictional']['ok'])
		self.assertIn('debug', checks['no-real-place-in-fictional'])

	# --- places-in-universe ---

	def test_all_real_places_reach_universe(self):
		universe = make_place(UNIVERSE_PLACE_ID, 'Universe')
		earth = make_place(1, 'Earth')
		london = make_place(2, 'London')
		checks = self._run_checks(
			[universe, earth, london],
			{earth.pk: [UNIVERSE_PLACE_ID], london.pk: [earth.pk]}
		)
		self.assertTrue(checks['places-in-universe']['ok'])

	def test_fictional_place_not_required_in_universe(self):
		universe = make_place(UNIVERSE_PLACE_ID, 'Universe')
		middle_earth = make_place(10, 'Middle-earth', fictional=True)
		earth = make_place(1, 'Earth')
		checks = self._run_checks(
			[universe, middle_earth, earth],
			{earth.pk: [UNIVERSE_PLACE_ID]}
			# middle_earth has no path to universe, but it's fictional — should pass
		)
		self.assertTrue(checks['places-in-universe']['ok'])

	def test_real_place_not_in_universe_fails(self):
		universe = make_place(UNIVERSE_PLACE_ID, 'Universe')
		earth = make_place(1, 'Earth')
		orphan = make_place(2, 'Orphan Island')
		checks = self._run_checks(
			[universe, earth, orphan],
			{earth.pk: [UNIVERSE_PLACE_ID]}
			# orphan has no contained_in links
		)
		self.assertFalse(checks['places-in-universe']['ok'])
		self.assertIn('Orphan Island', checks['places-in-universe']['debug'])

	def test_universe_missing_fails(self):
		earth = make_place(1, 'Earth')
		checks = self._run_checks([earth], {})
		self.assertFalse(checks['places-in-universe']['ok'])
		self.assertIn('not found', checks['places-in-universe']['debug'])

	def test_places_in_universe_skipped_when_cycle(self):
		a = make_place(1, 'A')
		b = make_place(2, 'B')
		checks = self._run_checks(
			[a, b],
			{a.pk: [b.pk], b.pk: [a.pk]}
		)
		self.assertFalse(checks['places-in-universe']['ok'])
		self.assertIn('Skipped', checks['places-in-universe']['debug'])


class WikipediaSlugChecksTest(SimpleTestCase):

	def test_all_valid_slugs_passes(self):
		models_with_slugs = [
			('Place', 1, 'London'),
			('Person', 2, 'Isles_of_Scilly'),
		]
		result = _check_no_invalid_wikipedia_slugs(models_with_slugs)
		self.assertTrue(result['ok'])

	def test_empty_list_passes(self):
		result = _check_no_invalid_wikipedia_slugs([])
		self.assertTrue(result['ok'])

	def test_slug_with_space_fails(self):
		models_with_slugs = [
			('Place', 42, 'Isles of Scilly'),
		]
		result = _check_no_invalid_wikipedia_slugs(models_with_slugs)
		self.assertFalse(result['ok'])
		self.assertIn('Isles of Scilly', result['debug'])
		self.assertIn('id=42', result['debug'])

	def test_slug_with_other_invalid_chars_fails(self):
		models_with_slugs = [
			('Place', 1, 'Valid_Slug'),
			('Person', 2, 'Bad<Slug>'),
		]
		result = _check_no_invalid_wikipedia_slugs(models_with_slugs)
		self.assertFalse(result['ok'])
		self.assertIn('Bad<Slug>', result['debug'])

	def test_get_wikipedia_slug_check_returns_valid_structure(self):
		result = get_wikipedia_slug_check()
		self.assertIn('ok', result)
		self.assertIn('techDetail', result)


class FestivalPeriodValidationTest(TestCase):
	"""FestivalPeriod.clean() rejects ambiguous shape combinations.

	See the table in FestivalPeriod's docstring for the full set of valid and
	invalid (start_day, duration_days) combinations.
	"""

	@classmethod
	def setUpTestData(cls):
		cls.calendar = Calendar.objects.create(name='Gregorian')
		cls.month = Month.objects.create(name='December', calendar=cls.calendar, order_in_calendar=12)
		cls.festival = Festival.objects.create(name='Christmas', day_of_month=25, month=cls.month)

	def _build(self, *, start_day, duration_days):
		return FestivalPeriod(
			name='test period',
			festival=self.festival,
			start_day=start_day,
			start_month=self.month,
			duration_days=duration_days,
		)

	def test_whole_month_period_is_valid(self):
		"""start_day null + duration_days null = the whole start_month."""
		self._build(start_day=None, duration_days=None).full_clean()

	def test_single_day_period_is_valid(self):
		"""start_day set + duration_days null = a single day."""
		self._build(start_day=25, duration_days=None).full_clean()

	def test_explicit_span_period_is_valid(self):
		"""start_day set + duration_days set = a span starting on start_day."""
		self._build(start_day=25, duration_days=8).full_clean()

	def test_duration_without_start_day_is_rejected(self):
		"""start_day null + duration_days set has no anchored meaning."""
		with self.assertRaises(ValidationError) as cm:
			self._build(start_day=None, duration_days=8).full_clean()
		self.assertIn('duration_days', cm.exception.error_dict)


# ─── Language Family URL Tests ──────────────────────────────────────────────────

class LanguageFamilyUrlTest(TestCase):
	"""LanguageFamily.get_absolute_url returns local URIs for synthetic families."""

	def test_qli_uses_local_uri(self):
		family = LanguageFamily(code='qli', name='language isolates')
		url = family.get_absolute_url()
		self.assertIn('/metadata/languagefamily/qli/', url)
		self.assertNotIn('id.loc.gov', url)

	def test_qsp_uses_local_uri(self):
		family = LanguageFamily(code='qsp', name='ISO 639 special codes')
		url = family.get_absolute_url()
		self.assertIn('/metadata/languagefamily/qsp/', url)
		self.assertNotIn('id.loc.gov', url)

	def test_standard_family_uses_loc_uri(self):
		family = LanguageFamily(code='gem', name='Germanic languages')
		url = family.get_absolute_url()
		self.assertEqual(url, 'http://id.loc.gov/vocabulary/iso639-5/gem')


class LanguageFamilyWebhookUrlTest(TestCase):
	"""LanguageFamily.get_webhook_url always returns an eolas-hosted URL.

	get_absolute_url() returns the LoC canonical URI for standard families, but
	arachne cannot ingest LoC's JSON-LD (wrong type vocabularies). The webhook
	URL must always point at eolas so arachne fetches eolas's own RDF.
	"""

	def test_standard_family_webhook_url_is_eolas_hosted(self):
		family = LanguageFamily(code='gem', name='Germanic languages')
		url = family.get_webhook_url()
		self.assertIn('/metadata/languagefamily/gem/', url)
		self.assertNotIn('id.loc.gov', url)

	def test_synthetic_family_webhook_url_matches_absolute_url(self):
		family = LanguageFamily(code='qli', name='language isolates')
		self.assertEqual(family.get_webhook_url(), family.get_absolute_url())

	def test_base_model_webhook_url_defaults_to_absolute_url(self):
		"""EolasModel.get_webhook_url defaults to get_absolute_url for models that don't override it."""
		from lucos_eolas.metadata.models import Weather
		item = Weather(name='Sunny')
		self.assertEqual(item.get_webhook_url(), item.get_absolute_url())


# ─── load_language_families Management Command Tests ─────────────────────────────

class LoadLanguageFamiliesSpecialCodesTest(TestCase):
	"""_process_special_codes creates the qsp family and zxx language."""

	def setUp(self):
		from lucos_eolas.metadata.management.commands.load_language_families import Command
		self.command = Command()
		self.command.stdout = open('/dev/null', 'w')
		self.command.style = type('style', (), {
			'SUCCESS': lambda self, s: s,
			'WARNING': lambda self, s: s,
		})()

	def tearDown(self):
		self.command.stdout.close()

	def test_creates_qsp_family(self):
		self.command._process_special_codes()
		family = LanguageFamily.objects.get(code='qsp')
		self.assertEqual(family.name, 'ISO 639 special codes')
		self.assertIsNone(family.parent)

	def test_creates_zxx_language(self):
		self.command._process_special_codes()
		lang = Language.objects.get(code='zxx')
		self.assertEqual(lang.name, 'No linguistic content')
		self.assertEqual(lang.family.code, 'qsp')

	def test_idempotent_on_rerun(self):
		"""Running _process_special_codes twice should not raise or duplicate."""
		self.command._process_special_codes()
		self.command._process_special_codes()
		self.assertEqual(LanguageFamily.objects.filter(code='qsp').count(), 1)
		self.assertEqual(Language.objects.filter(code='zxx').count(), 1)


# ─── TransportMode Tests ───────────────────────────────────────────────────────

class TransportModeStrTest(TestCase):
	"""TransportMode.__str__ returns the name in title case."""

	def test_str_returns_title_case(self):
		mode = TransportMode(name='train', plural='trains')
		self.assertEqual(str(mode), 'Train')

	def test_str_already_title_case(self):
		mode = TransportMode(name='Aeroplane', plural='aeroplanes')
		self.assertEqual(str(mode), 'Aeroplane')

	def test_str_multi_word(self):
		mode = TransportMode(name='hot air balloon', plural='hot air balloons')
		self.assertEqual(str(mode), 'Hot Air Balloon')


# ─── Vehicle Tests ─────────────────────────────────────────────────────────────

class VehicleStrTest(TestCase):
	"""Vehicle.__str__ disambiguation: shows type in parentheses only when name is shared."""

	@classmethod
	def setUpTestData(cls):
		cls.boat = TransportMode.objects.create(name='boat', plural='boats')
		cls.train = TransportMode.objects.create(name='train', plural='trains')

	def test_unique_name_returns_just_name(self):
		"""A vehicle whose name is unique returns just its name."""
		vehicle = Vehicle.objects.create(name='Titanic', type=self.boat)
		self.assertEqual(str(vehicle), 'Titanic')

	def test_shared_name_includes_type(self):
		"""When two vehicles share a name, str() disambiguates with the type."""
		Vehicle.objects.create(name='Discovery', type=self.boat)
		discovery_train = Vehicle.objects.create(name='Discovery', type=self.train)
		self.assertIn('(', str(discovery_train))
		self.assertIn('Discovery', str(discovery_train))
		self.assertIn('Train', str(discovery_train))

	def test_fictional_vehicle_can_be_created(self):
		"""fictional=True is accepted and stored correctly."""
		vehicle = Vehicle.objects.create(
			name='Chitty Chitty Bang Bang',
			type=self.boat,  # type used for convenience; fictional cars aren't boats, but test only cares about fictional flag
			fictional=True,
		)
		self.assertTrue(vehicle.fictional)


# ─── Parent-class prefLabel Tests ────────────────────────────────────────────

class PlaceTypeParentClassLabelTest(SimpleTestCase):
	"""PlaceType.get_rdf emits skos:prefLabel for schema:Place when include_type_label=True."""

	def test_parent_class_english_label_emitted(self):
		import rdflib
		place_type = PlaceType(name='City', plural='Cities', category='Terrestrial')
		g = place_type.get_rdf(include_type_label=True)
		self.assertIn(
			(rdflib.SDO.Place, rdflib.SKOS.prefLabel, rdflib.Literal("Place", lang="en")),
			g,
			"Expected English prefLabel for schema:Place in the graph",
		)

	def test_parent_class_label_not_emitted_without_type_label(self):
		import rdflib
		place_type = PlaceType(name='City', plural='Cities', category='Terrestrial')
		g = place_type.get_rdf(include_type_label=False)
		matching = [(s, p, o) for s, p, o in g if s == rdflib.SDO.Place and p == rdflib.SKOS.prefLabel]
		self.assertEqual(matching, [], "No prefLabel for schema:Place when include_type_label=False")


class CreativeWorkTypeParentClassLabelTest(SimpleTestCase):
	"""CreativeWorkType.get_rdf emits skos:prefLabel for schema:CreativeWork when include_type_label=True."""

	def test_parent_class_english_label_emitted(self):
		import rdflib
		cw_type = CreativeWorkType(name='Film', plural='Films', category='Dramaturgical')
		g = cw_type.get_rdf(include_type_label=True)
		self.assertIn(
			(rdflib.SDO.CreativeWork, rdflib.SKOS.prefLabel, rdflib.Literal("Creative Work", lang="en")),
			g,
			"Expected English prefLabel for schema:CreativeWork in the graph",
		)

	def test_parent_class_label_not_emitted_without_type_label(self):
		import rdflib
		cw_type = CreativeWorkType(name='Film', plural='Films', category='Dramaturgical')
		g = cw_type.get_rdf(include_type_label=False)
		matching = [(s, p, o) for s, p, o in g if s == rdflib.SDO.CreativeWork and p == rdflib.SKOS.prefLabel]
		self.assertEqual(matching, [], "No prefLabel for schema:CreativeWork when include_type_label=False")


class TransportModeParentClassLabelTest(SimpleTestCase):
	"""TransportMode.get_rdf emits skos:prefLabel for dbpedia:MeanOfTransportation when include_type_label=True."""

	def test_parent_class_english_label_emitted(self):
		import rdflib
		DBPEDIA_NS = rdflib.Namespace("https://dbpedia.org/ontology/")
		transport_mode = TransportMode(name='Car', plural='Cars')
		g = transport_mode.get_rdf(include_type_label=True)
		self.assertIn(
			(DBPEDIA_NS.MeanOfTransportation, rdflib.SKOS.prefLabel, rdflib.Literal("Means of Transport", lang="en")),
			g,
			"Expected English prefLabel for dbpedia:MeanOfTransportation in the graph",
		)

	def test_parent_class_label_not_emitted_without_type_label(self):
		import rdflib
		DBPEDIA_NS = rdflib.Namespace("https://dbpedia.org/ontology/")
		transport_mode = TransportMode(name='Car', plural='Cars')
		g = transport_mode.get_rdf(include_type_label=False)
		matching = [(s, p, o) for s, p, o in g if s == DBPEDIA_NS.MeanOfTransportation and p == rdflib.SKOS.prefLabel]
		self.assertEqual(matching, [], "No prefLabel for dbpedia:MeanOfTransportation when include_type_label=False")


# ─── ThingCreate (POST /metadata/{type}/) Tests ───────────────────────────────

class ThingCreateEndpointTest(TestCase):
	"""POST /metadata/{type}/ — create entities programmatically."""

	AUTH = {'HTTP_AUTHORIZATION': 'key key'}
	JSON_CT = {'content_type': 'application/json'}

	def _post(self, type, body, auth=True, content_type='application/json'):
		headers = dict(self.AUTH) if auth else {}
		return self.client.post(
			f'/api/metadata/{type}/',
			data=json.dumps(body),
			content_type=content_type,
			**headers,
		)

	# ── Authentication ──────────────────────────────────────────────────────

	def test_no_auth_returns_401(self):
		response = self._post('person', {'name': 'J. S. Bach'}, auth=False)
		self.assertEqual(response.status_code, 401)

	def test_invalid_key_returns_403(self):
		response = self.client.post(
			'/api/metadata/person/',
			data=json.dumps({'name': 'J. S. Bach'}),
			content_type='application/json',
			HTTP_AUTHORIZATION='key wrongkey',
		)
		self.assertEqual(response.status_code, 403)

	def test_read_only_key_returns_403(self):
		# A key with only the 'eolas:read' scope must not be able to create entities.
		# The test CLIENT_KEYS has 'readonlykey' with scope 'eolas:read' only.
		response = self.client.post(
			'/api/metadata/person/',
			data=json.dumps({'name': 'J. S. Bach'}),
			content_type='application/json',
			HTTP_AUTHORIZATION='key readonlykey',
		)
		self.assertEqual(response.status_code, 403)

	# ── Content-Type ────────────────────────────────────────────────────────

	def test_wrong_content_type_returns_415(self):
		response = self._post('person', {'name': 'J. S. Bach'}, content_type='text/plain')
		self.assertEqual(response.status_code, 415)

	def test_form_encoded_content_type_returns_415(self):
		response = self._post('person', {'name': 'J. S. Bach'}, content_type='application/x-www-form-urlencoded')
		self.assertEqual(response.status_code, 415)

	# ── Method ──────────────────────────────────────────────────────────────

	def test_get_returns_405(self):
		response = self.client.get('/api/metadata/person/', **self.AUTH)
		self.assertEqual(response.status_code, 405)

	# ── Type validation ─────────────────────────────────────────────────────

	def test_unknown_type_returns_404(self):
		response = self._post('unknowntype', {'name': 'Test'})
		self.assertEqual(response.status_code, 404)

	# ── Field validation ────────────────────────────────────────────────────

	def test_missing_name_returns_400(self):
		response = self._post('person', {})
		self.assertEqual(response.status_code, 400)
		self.assertIn('error', response.json())

	def test_empty_name_returns_400(self):
		response = self._post('person', {'name': '   '})
		self.assertEqual(response.status_code, 400)
		self.assertIn('error', response.json())

	def test_non_string_name_returns_400(self):
		response = self._post('person', {'name': 42})
		self.assertEqual(response.status_code, 400)

	def test_invalid_json_returns_400(self):
		response = self.client.post(
			'/api/metadata/person/',
			data=b'not-json',
			content_type='application/json',
			**self.AUTH,
		)
		self.assertEqual(response.status_code, 400)

	# ── Successful creation ──────────────────────────────────────────────────

	@patch('lucos_eolas.metadata.signals.updateLoganne')
	def test_creates_person_and_returns_201(self, mock_loganne):
		response = self._post('person', {'name': 'Johann Sebastian Bach'})
		self.assertEqual(response.status_code, 201)
		data = response.json()
		self.assertIn('id', data)
		self.assertIn('name', data)
		self.assertIn('uri', data)
		self.assertEqual(data['name'], 'Johann Sebastian Bach')
		self.assertIn('/metadata/person/', data['uri'])
		self.assertTrue(Person.objects.filter(name='Johann Sebastian Bach').exists())

	@patch('lucos_eolas.metadata.signals.updateLoganne')
	def test_response_name_is_normalised(self, mock_loganne):
		"""Response 'name' comes from str(obj), which may differ from submitted value."""
		response = self._post('person', {'name': '  Ludwig van Beethoven  '})
		self.assertEqual(response.status_code, 201)
		data = response.json()
		# Submitted name is stripped; str(Person) returns the stored name
		self.assertEqual(data['name'], 'Ludwig van Beethoven')

	@patch('lucos_eolas.metadata.signals.updateLoganne')
	def test_creates_person_with_optional_fields(self, mock_loganne):
		response = self._post('person', {
			'name': 'Sherlock Holmes',
			'fictional': True,
			'wikipedia_slug': 'Sherlock_Holmes',
		})
		self.assertEqual(response.status_code, 201)
		person = Person.objects.get(name='Sherlock Holmes')
		self.assertTrue(person.fictional)
		self.assertEqual(person.wikipedia_slug, 'Sherlock_Holmes')

	@patch('lucos_eolas.metadata.signals.updateLoganne')
	def test_unknown_fields_in_body_are_ignored(self, mock_loganne):
		"""Fields not on the model should be silently ignored (not raise an error)."""
		response = self._post('person', {
			'name': 'Agatha Christie',
			'nonexistent_field': 'some value',
		})
		self.assertEqual(response.status_code, 201)
		self.assertTrue(Person.objects.filter(name='Agatha Christie').exists())

	@patch('lucos_eolas.metadata.signals.updateLoganne')
	def test_loganne_itemcreated_fired(self, mock_loganne):
		with self.captureOnCommitCallbacks(execute=True):
			self._post('person', {'name': 'Charles Darwin'})
		called_types = [call.kwargs.get('type') for call in mock_loganne.call_args_list]
		self.assertIn('itemCreated', called_types)

	@patch('lucos_eolas.metadata.signals.updateLoganne')
	def test_loganne_itemcreated_includes_entity_type(self, mock_loganne):
		with self.captureOnCommitCallbacks(execute=True):
			self._post('person', {'name': 'Marie Curie'})
		item_type = Person._meta.verbose_name.title()
		created_calls = [c for c in mock_loganne.call_args_list if c.kwargs.get('type') == 'itemCreated']
		self.assertTrue(len(created_calls) > 0, 'itemCreated should have been fired')
		self.assertEqual(created_calls[0].kwargs['itemType'], item_type)

	@patch('lucos_eolas.metadata.signals.updateLoganne')
	def test_loganne_itemupdated_includes_entity_type(self, mock_loganne):
		person = Person.objects.create(name='Isaac Newton')
		mock_loganne.reset_mock()
		with self.captureOnCommitCallbacks(execute=True):
			person.name = 'Sir Isaac Newton'
			person.save()
		item_type = Person._meta.verbose_name.title()
		updated_calls = [c for c in mock_loganne.call_args_list if c.kwargs.get('type') == 'itemUpdated']
		self.assertTrue(len(updated_calls) > 0, 'itemUpdated should have been fired')
		self.assertEqual(updated_calls[0].kwargs['itemType'], item_type)

	@patch('lucos_eolas.metadata.signals.updateLoganne')
	def test_loganne_itemdeleted_includes_entity_type(self, mock_loganne):
		person = Person.objects.create(name='Galileo Galilei')
		mock_loganne.reset_mock()
		with self.captureOnCommitCallbacks(execute=True):
			person.delete()
		item_type = Person._meta.verbose_name.title()
		deleted_calls = [c for c in mock_loganne.call_args_list if c.kwargs.get('type') == 'itemDeleted']
		self.assertTrue(len(deleted_calls) > 0, 'itemDeleted should have been fired')
		self.assertEqual(deleted_calls[0].kwargs['itemType'], item_type)

	@patch('lucos_eolas.metadata.signals.updateLoganne')
	def test_creates_person_with_alternate_names(self, mock_loganne):
		response = self._post('person', {
			'name': 'Samuel Clemens',
			'alternate_names': ['Mark Twain'],
		})
		self.assertEqual(response.status_code, 201)
		person = Person.objects.get(name='Samuel Clemens')
		self.assertIn('Mark Twain', person.alternate_names)

	def test_invalid_alternate_names_returns_400(self):
		"""alternate_names must be a list, not a string or other scalar."""
		response = self._post('person', {
			'name': 'Agatha Christie',
			'alternate_names': 'not-a-list',
		})
		self.assertEqual(response.status_code, 400)

	# ── Duplicate detection ──────────────────────────────────────────────────

	@patch('lucos_eolas.metadata.signals.updateLoganne')
	def test_duplicate_name_returns_409(self, mock_loganne):
		existing = Person.objects.create(name='Wolfgang Amadeus Mozart')
		response = self._post('person', {'name': 'Wolfgang Amadeus Mozart'})
		self.assertEqual(response.status_code, 409)
		data = response.json()
		self.assertEqual(data['error'], 'already_exists')
		self.assertEqual(data['id'], existing.pk)
		self.assertIn('/metadata/person/', data['uri'])

	@patch('lucos_eolas.metadata.signals.updateLoganne')
	def test_duplicate_check_is_case_insensitive(self, mock_loganne):
		existing = Person.objects.create(name='Franz Liszt')
		response = self._post('person', {'name': 'franz liszt'})
		self.assertEqual(response.status_code, 409)
		data = response.json()
		self.assertEqual(data['id'], existing.pk)

	@patch('lucos_eolas.metadata.signals.updateLoganne')
	def test_multiple_existing_same_name_does_not_block_creation(self, mock_loganne):
		"""When multiple entities share a name, a new one is created (ambiguous — let admin merge)."""
		Person.objects.create(name='John Smith')
		Person.objects.create(name='John Smith')
		response = self._post('person', {'name': 'John Smith'})
		self.assertEqual(response.status_code, 201)
		self.assertEqual(Person.objects.filter(name='John Smith').count(), 3)

	# ── FK attname fields ────────────────────────────────────────────────────

	@patch('lucos_eolas.metadata.signals.updateLoganne')
	def test_creates_entity_with_fk_via_attname(self, mock_loganne):
		"""FK fields accepted via their attname (e.g. type_id) so callers can set
		mandatory FK fields without needing a URI lookup."""
		cw_type = CreativeWorkType.objects.create(
			name='Film', plural='Films', category='Dramaturgical',
		)
		response = self._post('creativework', {
			'name': 'Casablanca',
			'type_id': cw_type.pk,
		})
		self.assertEqual(response.status_code, 201)
		data = response.json()
		self.assertIn('id', data)
		self.assertIn('/metadata/creativework/', data['uri'])
		cw = CreativeWork.objects.get(name='Casablanca')
		self.assertEqual(cw.type_id, cw_type.pk)

	def test_invalid_fk_attname_value_returns_400(self):
		"""Passing a non-existent FK ID should fail validation rather than crash."""
		response = self._post('creativework', {
			'name': 'The Phantom Film',
			'type_id': 99999,
		})
		self.assertEqual(response.status_code, 400)

	@patch('lucos_eolas.metadata.signals.updateLoganne')
	def test_missing_required_fk_returns_400(self, mock_loganne):
		"""Creating an entity whose model requires a FK without providing it returns 400."""
		response = self._post('creativework', {'name': 'No Type Film'})
		self.assertEqual(response.status_code, 400)


# ─── Admin Duplicate Name Confirmation Tests ──────────────────────────────────

@override_settings(AUTHENTICATION_BACKENDS=['django.contrib.auth.backends.ModelBackend'])
class DuplicateNameConfirmationTest(TestCase):
	"""EolasModelAdmin shows a confirmation page when creating an item with a duplicate name."""

	def setUp(self):
		user = User.objects.create_superuser('testadmin', 'admin@test.com', 'password')
		self.client.force_login(user, backend='django.contrib.auth.backends.ModelBackend')

	def test_create_with_duplicate_name_shows_confirmation(self):
		"""POST with a name matching an existing item renders the confirmation page."""
		HistoricalEvent.objects.create(name='World War II')
		response = self.client.post('/metadata/historicalevent/add/', {'name': 'World War II'})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Duplicate name found')
		self.assertContains(response, 'World War II')

	def test_duplicate_check_is_case_insensitive(self):
		"""The confirmation is shown even when the submitted name differs in case."""
		HistoricalEvent.objects.create(name='World War II')
		response = self.client.post('/metadata/historicalevent/add/', {'name': 'world war ii'})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Duplicate name found')

	def test_unique_name_does_not_show_confirmation(self):
		"""POST with a unique name redirects after creation — never shows the duplicate confirmation."""
		response = self.client.post('/metadata/historicalevent/add/', {'name': 'Totally Unique Event'})
		# 302 = form saved and redirected; confirmation page is always 200, so this is unambiguous
		self.assertEqual(response.status_code, 302)

	def test_confirm_duplicate_flag_bypasses_check(self):
		"""When _confirm_duplicate=1 is present, the duplicate check is skipped."""
		HistoricalEvent.objects.create(name='World War II')
		response = self.client.post('/metadata/historicalevent/add/', {
			'name': 'World War II',
			'_confirm_duplicate': '1',
		})
		# Duplicate check is skipped — admin shows form errors (missing fields), not confirmation
		self.assertEqual(response.status_code, 200)
		self.assertNotContains(response, 'Duplicate name found')

	def test_edit_without_name_change_no_confirmation(self):
		"""Saving an existing item with its current name redirects — no duplicate confirmation."""
		event = HistoricalEvent.objects.create(name='World War I')
		response = self.client.post(
			f'/metadata/historicalevent/{event.pk}/change/',
			{'name': 'World War I'},
		)
		# 302 = saved and redirected; confirmation page is always 200, so this is unambiguous
		self.assertEqual(response.status_code, 302)

	def test_multiple_duplicates_all_listed(self):
		"""When more than one item matches, all are listed on the confirmation page."""
		Person.objects.create(name='John Smith')
		Person.objects.create(name='John Smith')
		response = self.client.post('/metadata/person/add/', {'name': 'John Smith'})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Duplicate name found')

	def test_alternate_name_match_shows_confirmation(self):
		"""A submitted name that matches an existing item's alternate name triggers confirmation."""
		HistoricalEvent.objects.create(name='Second World War', alternate_names=['World War II'])
		response = self.client.post('/metadata/historicalevent/add/', {'name': 'World War II'})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Duplicate name found')

	def test_alternate_name_check_is_case_insensitive(self):
		"""Alternate-name match is also case-insensitive."""
		HistoricalEvent.objects.create(name='Second World War', alternate_names=['World War II'])
		response = self.client.post('/metadata/historicalevent/add/', {'name': 'world war ii'})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, 'Duplicate name found')

	def test_confirmation_page_contains_link_to_existing_item(self):
		"""The confirmation page links to the existing item's change page."""
		event = HistoricalEvent.objects.create(name='World War II')
		response = self.client.post('/metadata/historicalevent/add/', {'name': 'World War II'})
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, f'/metadata/historicalevent/{event.pk}/change/')


# ─── ArrayWidget Tests ────────────────────────────────────────────────────────

class ArrayWidgetFormatValueTest(SimpleTestCase):
	"""ArrayWidget.format_value() must split comma-separated strings back into lists.

	SimpleArrayField.prepare_value() joins a Python list to a comma-separated
	string before passing the value to the widget for rendering.  Without this
	split, optgroups() would receive ['foo,bar'] (one element) and render a
	single chip containing a comma rather than two separate chips.
	"""

	def test_splits_comma_separated_string(self):
		w = ArrayWidget()
		self.assertEqual(w.format_value('London,Londres'), ['London', 'Londres'])

	def test_splits_three_values(self):
		w = ArrayWidget()
		self.assertEqual(
			w.format_value('London,Londres,Lunden'),
			['London', 'Londres', 'Lunden'],
		)

	def test_strips_whitespace_around_values(self):
		w = ArrayWidget()
		self.assertEqual(w.format_value('London , Londres'), ['London', 'Londres'])

	def test_empty_string_returns_empty_list(self):
		w = ArrayWidget()
		self.assertEqual(w.format_value(''), [])

	def test_none_returns_empty_list(self):
		w = ArrayWidget()
		self.assertEqual(w.format_value(None), [])

	def test_list_passes_through_unchanged(self):
		"""If value is already a list (e.g. from initial=), pass it through."""
		w = ArrayWidget()
		self.assertEqual(w.format_value(['London', 'Londres']), ['London', 'Londres'])


class ArrayWidgetValueFromDatadictTest(SimpleTestCase):
	"""ArrayWidget.value_from_datadict() must rejoin POST values for SimpleArrayField."""

	def test_joins_multiple_values_with_comma(self):
		w = ArrayWidget()
		qd = QueryDict('f=London&f=Londres&f=Lunden')
		self.assertEqual(w.value_from_datadict(qd, {}, 'f'), 'London,Londres,Lunden')

	def test_single_value(self):
		w = ArrayWidget()
		qd = QueryDict('f=London')
		self.assertEqual(w.value_from_datadict(qd, {}, 'f'), 'London')

	def test_empty_returns_empty_string(self):
		w = ArrayWidget()
		qd = QueryDict('')
		self.assertEqual(w.value_from_datadict(qd, {}, 'f'), '')

	def test_strips_whitespace_and_skips_blanks(self):
		w = ArrayWidget()
		qd = QueryDict('f=+London+&f=&f=+Paris+')
		self.assertEqual(w.value_from_datadict(qd, {}, 'f'), 'London,Paris')


class ArrayWidgetRenderTest(SimpleTestCase):
	"""ArrayWidget.render() must produce correct HTML for both empty and populated values."""

	def test_render_existing_values_as_selected_options(self):
		"""Each existing value must appear as a selected <option>."""
		w = ArrayWidget()
		html = w.render('alternate_names', 'London,Londres', attrs={'id': 'id_alternate_names'})
		self.assertIn('value="London"', html)
		self.assertIn('value="Londres"', html)
		self.assertIn('selected', html)
		self.assertIn('class="array-field-input"', html)

	def test_render_empty_value_produces_bare_select(self):
		"""An empty value renders a <select> with no <option> elements."""
		w = ArrayWidget()
		html = w.render('alternate_names', '', attrs={'id': 'id_alternate_names'})
		self.assertNotIn('<option', html)
		self.assertIn('<select', html)

	def test_render_none_produces_bare_select(self):
		w = ArrayWidget()
		html = w.render('alternate_names', None, attrs={'id': 'id_alternate_names'})
		self.assertNotIn('<option', html)

	def test_each_value_is_its_own_option(self):
		"""Three values must produce three separate <option> elements, not one."""
		w = ArrayWidget()
		html = w.render('alternate_names', 'a,b,c', attrs={'id': 'id_alternate_names'})
		self.assertEqual(html.count('<option'), 3)


# ─── Loganne Real-Transport Tests ─────────────────────────────────────────────

@override_settings(AUTHENTICATION_BACKENDS=['django.contrib.auth.backends.ModelBackend'])
class LoganneRealTransportTest(TestCase):
	"""Drive the real loganne client against a stubbed HTTP transport.

	These tests verify that `level` is correctly passed to `updateLoganne` after
	the v2 client made it a required parameter.  They use requests-mock (which
	intercepts at the HTTPAdapter level) rather than mocking `updateLoganne`
	itself, so a missing or invalid `level` arg causes the test to fail before
	any HTTP call is made — catching the integration gap that module-level mocks
	cannot.
	"""

	def setUp(self):
		user = User.objects.create_superuser('realadmin', 'rta@test.com', 'pass')
		self.client.force_login(user, backend='django.contrib.auth.backends.ModelBackend')

	def test_item_created_signal_posts_notable_level(self):
		"""Creating an entity fires itemCreated with level='notable' over HTTP."""
		import requests_mock as requests_mock_lib
		from loganne import LOGANNE_ENDPOINT

		with requests_mock_lib.Mocker() as m:
			m.post(LOGANNE_ENDPOINT, json={})
			with self.captureOnCommitCallbacks(execute=True):
				DayOfWeek.objects.create(name='Monday', order=1)

		self.assertTrue(m.called, 'Expected an HTTP POST to loganne')
		payload = m.last_request.json()
		self.assertEqual(payload['type'], 'itemCreated')
		self.assertEqual(payload['level'], 'notable')

	def test_item_deleted_signal_posts_routine_level(self):
		"""Deleting an entity fires itemDeleted with level='routine' over HTTP."""
		import requests_mock as requests_mock_lib
		from loganne import LOGANNE_ENDPOINT

		day = DayOfWeek.objects.create(name='Tuesday', order=2)
		with requests_mock_lib.Mocker() as m:
			m.post(LOGANNE_ENDPOINT, json={})
			with self.captureOnCommitCallbacks(execute=True):
				day.delete()

		self.assertTrue(m.called, 'Expected an HTTP POST to loganne')
		payload = m.last_request.json()
		self.assertEqual(payload['type'], 'itemDeleted')
		self.assertEqual(payload['level'], 'routine')

	def test_item_merged_admin_action_posts_routine_level(self):
		"""The merge_entities admin action fires itemMerged with level='routine' over HTTP."""
		import requests_mock as requests_mock_lib
		from loganne import LOGANNE_ENDPOINT

		source = HistoricalEvent.objects.create(name='Event Alpha')
		target = HistoricalEvent.objects.create(name='Event Beta')
		with requests_mock_lib.Mocker() as m:
			m.post(LOGANNE_ENDPOINT, json={})
			self.client.post(
				'/metadata/historicalevent/',
				{
					'action': 'merge_entities',
					'_selected_action': [str(source.pk), str(target.pk)],
					'apply_merge': '1',
					'target_id': str(target.pk),
				},
			)

		self.assertTrue(m.called, 'Expected an HTTP POST to loganne')
		payload = m.last_request.json()
		self.assertEqual(payload['type'], 'itemMerged')
		self.assertEqual(payload['level'], 'routine')


# ─── Case utility tests ────────────────────────────────────────────────────────

class SmartLowerTest(SimpleTestCase):
	"""smart_lower preserves all-uppercase words and lowercases the rest."""

	def test_acronym_preserved(self):
		"""An all-uppercase word is kept uppercase."""
		self.assertEqual(smart_lower('TV Programme'), 'TV programme')

	def test_multiple_acronyms(self):
		"""Multiple acronyms in one string are all preserved."""
		self.assertEqual(smart_lower('BBC TV documentary'), 'BBC TV documentary')

	def test_normal_words_lowercased(self):
		"""Mixed-case non-acronym words are lowercased."""
		self.assertEqual(smart_lower('Road'), 'road')

	def test_already_lowercase(self):
		"""Already-lowercase text is unchanged."""
		self.assertEqual(smart_lower('tv programme'), 'tv programme')

	def test_single_acronym(self):
		"""A single all-uppercase word is preserved."""
		self.assertEqual(smart_lower('BBC'), 'BBC')

	def test_single_lowercase_word(self):
		"""A single lowercase word is unchanged."""
		self.assertEqual(smart_lower('road'), 'road')

	def test_title_case_word_lowercased(self):
		"""A title-cased word (not all-uppercase) is lowercased."""
		self.assertEqual(smart_lower('Programme'), 'programme')


class SmartTitleTest(SimpleTestCase):
	"""smart_title capitalises the first letter of each word, preserving acronyms."""

	def test_acronym_preserved(self):
		"""An all-uppercase word is kept uppercase."""
		self.assertEqual(smart_title('TV programme'), 'TV Programme')

	def test_multiple_acronyms(self):
		"""Multiple acronyms in one string are all preserved."""
		self.assertEqual(smart_title('BBC TV documentary'), 'BBC TV Documentary')

	def test_normal_words_capitalised(self):
		"""Ordinary lowercase words are title-cased."""
		self.assertEqual(smart_title('road'), 'Road')

	def test_already_lowercase_acronym_lost(self):
		"""A word that was stored lowercase (acronym info lost) title-cases like .title()."""
		self.assertEqual(smart_title('tv programme'), 'Tv Programme')

	def test_single_acronym(self):
		"""A single all-uppercase word is preserved."""
		self.assertEqual(smart_title('BBC'), 'BBC')

	def test_single_lowercase_word(self):
		"""A single lowercase word is capitalised."""
		self.assertEqual(smart_title('road'), 'Road')
