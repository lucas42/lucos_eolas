"""
Data consistency checks for the /_info endpoint.
"""

UNIVERSE_PLACE_ID = 373


def get_place_consistency_checks():
	"""
	Returns a dict of check results suitable for the /_info `checks` field.

	Runs three checks:
	  - places-in-universe: every non-fictional real place is reachable from
	    Universe (id=373) via transitive contained_in links
	  - no-real-place-in-fictional: no real place has a contained_in link to
	    a fictional place
	  - no-circular-containment: the contained_in graph has no cycles
	"""
	from .models import Place

	# Load all places and their contained_in links in two queries
	all_places = {p.pk: p for p in Place.objects.all()}

	# Build adjacency map: place_id -> set of contained_in place_ids
	# Using prefetch to avoid per-place queries
	containment = {pk: set() for pk in all_places}
	for place in Place.objects.prefetch_related('contained_in'):
		for parent in place.contained_in.all():
			containment[place.pk].add(parent.pk)

	checks = {}

	# --- Check 1: no circular contained_in hierarchies ---
	# DFS with visited (fully processed) and in_stack (currently being explored)
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
			has_cycle(place_id)

	if cycle_found:
		example_name = all_places[cycle_example].name if cycle_example in all_places else str(cycle_example)
		checks['no-circular-containment'] = {
			'ok': False,
			'techDetail': 'Checks that the contained_in hierarchy has no circular references',
			'debug': f'Cycle detected involving place: {example_name} (id={cycle_example})',
		}
	else:
		checks['no-circular-containment'] = {
			'ok': True,
			'techDetail': 'Checks that the contained_in hierarchy has no circular references',
		}

	# --- Check 2: no real place contained_in a fictional place ---
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
		checks['no-real-place-in-fictional'] = {
			'ok': False,
			'techDetail': 'Checks that no real place is directly contained_in a fictional place',
			'debug': f'Violations: {examples}',
		}
	else:
		checks['no-real-place-in-fictional'] = {
			'ok': True,
			'techDetail': 'Checks that no real place is directly contained_in a fictional place',
		}

	# --- Check 3: all non-fictional places are reachable from Universe ---
	# Only meaningful if no cycles (cycles would cause infinite traversal otherwise)
	if not cycle_found:
		# Build reverse map: place_id -> set of places it contains (i.e. contained_in links pointing to it)
		# We want to find all places reachable FROM universe going downward (contains direction)
		# Equivalently: find all places that can reach Universe going upward (contained_in direction)
		# BFS upward from each non-fictional place would be O(n^2); instead do a single BFS/DFS
		# downward from Universe using the reverse (contains) edges.
		reverse_containment = {pk: set() for pk in all_places}
		for place_id, parents in containment.items():
			for parent_id in parents:
				if parent_id in reverse_containment:
					reverse_containment[parent_id].add(place_id)

		# BFS from Universe downward through contains edges
		if UNIVERSE_PLACE_ID in all_places:
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

			# Find non-fictional places not reachable from Universe (excluding Universe itself)
			unreachable = [
				p for pk, p in all_places.items()
				if not p.fictional and pk != UNIVERSE_PLACE_ID and pk not in reachable
			]

			if unreachable:
				examples = ', '.join(
					f'{p.name} (id={p.pk})' for p in unreachable[:5]
				)
				checks['places-in-universe'] = {
					'ok': False,
					'techDetail': 'Checks that all non-fictional places are reachable from Universe via transitive contained_in links',
					'debug': f'Not reachable from Universe: {examples}',
				}
			else:
				checks['places-in-universe'] = {
					'ok': True,
					'techDetail': 'Checks that all non-fictional places are reachable from Universe via transitive contained_in links',
				}
		else:
			checks['places-in-universe'] = {
				'ok': False,
				'techDetail': 'Checks that all non-fictional places are reachable from Universe via transitive contained_in links',
				'debug': f'Universe (id={UNIVERSE_PLACE_ID}) not found in database',
			}
	else:
		checks['places-in-universe'] = {
			'ok': False,
			'techDetail': 'Checks that all non-fictional places are reachable from Universe via transitive contained_in links',
			'debug': 'Skipped due to circular containment — fix cycles first',
		}

	return checks
