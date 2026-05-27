# lucos_eolas

## Canonical Names in Data Migrations

When writing a data migration that looks up existing rows by name (e.g. `TransportMode.objects.filter(name__iexact=...)`), you **must use the canonical `skos:prefLabel`** — not an alternate name.

In `lucos_eolas`, the `name` field stores the canonical name. In arachne, this corresponds to `skos:prefLabel`. The `rdfs:label` values in arachne are alternate names and are often returned first alphabetically by `mcp__arachne__find_entities` — **do not use these as the lookup key**.

To get the canonical name for an entity: use `mcp__arachne__get_entity(uri=...)` and read the `skos:prefLabel` field.

**Example:** The TransportMode "Helicopter" has alternate names "Chopper" and "Whirlybird". `find_entities` may return "Chopper" (alphabetically first). The correct migration entry is `('helicopter', 'helicopters')`, not `('chopper', 'choppers')`.

## Downstream consumers

**Ontology changes can have non-obvious effects on downstream consumers.** Arachne consumes this ontology to build its triplestore and search index, and several kinds of changes have known interactions. When making ontology changes — particularly adding new shapes to existing terms — cross-check [`lucos_arachne/CLAUDE.md`](https://github.com/lucas42/lucos_arachne/blob/main/CLAUDE.md). Known interactions include:

- **Adding `skos:prefLabel` to a predicate or class** can cause arachne's search ingestor to treat the term itself as an indexable item. (Resolved by `lucas42/lucos_arachne#544`'s namespace-based filter, but the broader principle stands: presence of human-readable labels can change what consumers think is "content".)
- **Adding `owl:inverseOf` on a high-fan-out predicate** causes the ingestor to materialise inverse closures into the inferred graph. For something like `dcterms:language`, this materialises one inferred triple per language tag per item — significant bloat.
- **Adding `owl:TransitiveProperty`** causes the ingestor to materialise transitive closures, with cost proportional to the depth and fan-out of the predicate.
- **Introducing a new domain `rdf:type`** requires the source's RDF export to include `skos:prefLabel` and `eolas:hasCategory` for that type — otherwise arachne's search-index ingestor will fail (see `lucas42/lucos_arachne#371` convention).
- **Any model that emits `rdfs:subClassOf` to a parent class must also emit `skos:prefLabel` for that parent class** (in all supported languages). Once arachne's subclass-aware ingestor (ADR-0004 Phase 2) walks subClassOf chains, it will call `get_label()` on every parent class it encounters — an unlabelled parent raises `ValueError`. The emitting model's `get_rdf(include_type_label=True)` is the right place to add these parent-class labels (see `PlaceType` and `CreativeWorkType` in `models.py` for examples).

This list is non-exhaustive. The general principle: ontology terms are consumed structurally by other systems, not just rendered; if a change alters the structural shape (new type, new property characteristic, new label, new inverse relationship), check the consumers.

## Migrations and Translations

When you change models in `lucos_eolas`, you **MUST NOT** run `makemigrations` directly. Instead:

1. **Modify Models**: Make your changes to `models.py`.
2. **Run the update script** from the project root:
   ```bash
   ./update.sh
   ```
   This script runs migrations and updates translation files inside Docker, then syncs them back to your local filesystem.
3. **Update Translations**: After running the script, check `app/lucos_eolas/locale/ga/LC_MESSAGES/django.po` and add any missing Irish translations.
4. **Never create migrations manually**: Do not run `python manage.py makemigrations` on the host or inside the container without using the script — it ensures proper sync and environment consistency.
