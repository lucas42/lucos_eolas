from django.test import SimpleTestCase, TestCase, override_settings
from django.contrib.auth.models import User
from unittest.mock import patch, MagicMock, call
from .checks import get_place_consistency_checks, get_wikipedia_slug_check, _check_no_invalid_wikipedia_slugs, UNIVERSE_PLACE_ID
from .models import DayOfWeek, Calendar, Month, HistoricalEvent
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
			type='entityMerged',
			humanReadable=f'{item_type} "Swearing" merged into "Profanity"',
			url=target_url,
			sourceUri=source_url,
			targetUri=target_url,
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
