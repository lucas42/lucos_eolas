# lucos_eolas

## Canonical Names in Data Migrations

When writing a data migration that looks up existing rows by name (e.g. `TransportMode.objects.filter(name__iexact=...)`), you **must use the canonical `skos:prefLabel`** — not an alternate name.

In `lucos_eolas`, the `name` field stores the canonical name. In arachne, this corresponds to `skos:prefLabel`. The `rdfs:label` values in arachne are alternate names and are often returned first alphabetically by `mcp__arachne__find_entities` — **do not use these as the lookup key**.

To get the canonical name for an entity: use `mcp__arachne__get_entity(uri=...)` and read the `skos:prefLabel` field.

**Example:** The TransportMode "Helicopter" has alternate names "Chopper" and "Whirlybird". `find_entities` may return "Chopper" (alphabetically first). The correct migration entry is `('helicopter', 'helicopters')`, not `('chopper', 'choppers')`.

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
