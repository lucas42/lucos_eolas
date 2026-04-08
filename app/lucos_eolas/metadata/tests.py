from django.test import SimpleTestCase
from unittest.mock import patch, MagicMock
from .checks import get_place_consistency_checks, get_wikipedia_slug_check, _check_no_invalid_wikipedia_slugs, UNIVERSE_PLACE_ID


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
