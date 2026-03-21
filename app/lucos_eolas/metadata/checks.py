"""
Data consistency checks for the /_info endpoint.
"""

UNIVERSE_PLACE_ID = 373


def _load_graph():
	"""Load all places and build the containment adjacency map in two queries."""
	from .models import Place
	all_places = {p.pk: p for p in Place.objects.all()}
	containment = {pk: set() for pk in all_places}
	for place in Place.objects.prefetch_related('contained_in'):
		for parent in place.contained_in.all():
			containment[place.pk].add(parent.pk)
	return all_places, containment


def _check_no_circular_containment(all_places, containment):
	"""Detect cycles in the contained_in graph using DFS."""
	visited = set()
	in_stack = set()
	cycle_found = False
	cycle_example = None

	def has_cycle(node_id):
		nonlocal cycle_found, cycle_example
		if node_id in in_stack:
			cycle_found = True
			cycle_example = node_id
			return True
		if node_id in visited:
			return False
		in_stack.add(node_id)
		for parent_id in containment.get(node_id, set()):
			if has_cycle(parent_id):
				return True
		in_stack.discard(node_id)
		visited.add(node_id)
		return False

	for place_id in all_places:
		if place_id not in visited:
			if has_cycle(place_id):
				break  # cycle found — no need to check further

	if cycle_found:
		example_name = all_places[cycle_example].name if cycle_example in all_places else str(cycle_example)
		return {
			'ok': False,
			'techDetail': 'Checks that the contained_in hierarchy has no circular references',
			'debug': f'Cycle detected involving place: {example_name} (id={cycle_example})',
		}
	return {
		'ok': True,
		'techDetail': 'Checks that the contained_in hierarchy has no circular references',
	}


def _check_no_real_place_in_fictional(all_places, containment):
	"""Check that no real place is directly contained_in a fictional place."""
	real_in_fictional = []
	for place in all_places.values():
		if not place.fictional:
			for parent_id in containment.get(place.pk, set()):
				parent = all_places.get(parent_id)
				if parent and parent.fictional:
					real_in_fictional.append((place, parent))

	if real_in_fictional:
		examples = ', '.join(
			f'{p.name} (id={p.pk}) contained_in {fp.name} (id={fp.pk})'
			for p, fp in real_in_fictional[:3]
		)
		return {
			'ok': False,
			'techDetail': 'Checks that no real place is directly contained_in a fictional place',
			'debug': f'Violations: {examples}',
		}
	return {
		'ok': True,
		'techDetail': 'Checks that no real place is directly contained_in a fictional place',
	}


def _check_places_in_universe(all_places, containment, cycle_found):
	"""Verify all non-fictional places are reachable from Universe via transitive contained_in."""
	if cycle_found:
		return {
			'ok': False,
			'techDetail': 'Checks that all non-fictional places are reachable from Universe via transitive contained_in links',
			'debug': 'Skipped due to circular containment — fix cycles first',
		}

	if UNIVERSE_PLACE_ID not in all_places:
		return {
			'ok': False,
			'techDetail': 'Checks that all non-fictional places are reachable from Universe via transitive contained_in links',
			'debug': f'Universe (id={UNIVERSE_PLACE_ID}) not found in database',
		}

	# Build reverse map (contains direction) for a single BFS downward from Universe
	reverse_containment = {pk: set() for pk in all_places}
	for place_id, parents in containment.items():
		for parent_id in parents:
			if parent_id in reverse_containment:
				reverse_containment[parent_id].add(place_id)

	reachable = set()
	queue = [UNIVERSE_PLACE_ID]
	while queue:
		current = queue.pop()
		if current in reachable:
			continue
		reachable.add(current)
		for child_id in reverse_containment.get(current, set()):
			if child_id not in reachable:
				queue.append(child_id)

	unreachable = [
		p for pk, p in all_places.items()
		if not p.fictional and pk != UNIVERSE_PLACE_ID and pk not in reachable
	]

	if unreachable:
		examples = ', '.join(f'{p.name} (id={p.pk})' for p in unreachable[:5])
		return {
			'ok': False,
			'techDetail': 'Checks that all non-fictional places are reachable from Universe via transitive contained_in links',
			'debug': f'Not reachable from Universe: {examples}',
		}
	return {
		'ok': True,
		'techDetail': 'Checks that all non-fictional places are reachable from Universe via transitive contained_in links',
	}


def get_place_consistency_checks():
	"""
	Returns a dict of check results suitable for the /_info `checks` field.

	Each check handles its own exceptions so a failure in one doesn't
	prevent the others from running.
	"""
	try:
		all_places, containment = _load_graph()
	except Exception as e:
		error_result = {'ok': False, 'techDetail': 'Could not load place data', 'debug': str(e)}
		return {
			'no-circular-containment': error_result,
			'no-real-place-in-fictional': error_result,
			'places-in-universe': error_result,
		}

	checks = {}

	try:
		checks['no-circular-containment'] = _check_no_circular_containment(all_places, containment)
	except Exception as e:
		checks['no-circular-containment'] = {
			'ok': False,
			'techDetail': 'Checks that the contained_in hierarchy has no circular references',
			'debug': str(e),
		}

	cycle_found = not checks['no-circular-containment']['ok']

	try:
		checks['no-real-place-in-fictional'] = _check_no_real_place_in_fictional(all_places, containment)
	except Exception as e:
		checks['no-real-place-in-fictional'] = {
			'ok': False,
			'techDetail': 'Checks that no real place is directly contained_in a fictional place',
			'debug': str(e),
		}

	try:
		checks['places-in-universe'] = _check_places_in_universe(all_places, containment, cycle_found)
	except Exception as e:
		checks['places-in-universe'] = {
			'ok': False,
			'techDetail': 'Checks that all non-fictional places are reachable from Universe via transitive contained_in links',
			'debug': str(e),
		}

	return checks
