# ADR-0001: lucos_eolas as the canonical home for cross-domain metadata entities

**Date:** 2026-05-31
**Status:** Proposed
**Discussion:** https://github.com/lucas42/lucos_arachne/issues/597 (artist/album boundary — see Scope below)

## Context

`lucos_eolas` is the estate's encyclopedic-entity service. Over the course of the media-metadata migration (a follow-on from the `lucos_media` v2→v3 work), a class of **cross-domain, non-media-specific** metadata was moved out of `lucos_media_metadata_api` and into `lucos_eolas` as its canonical home: people (composers, producers), places, content-warning classifications, themes/temporal entities, memories, languages, and related encyclopedic types. `lucos_media_metadata_api` retains only **media-specific** concerns (tracks, collections, albums, artists) and now references eolas entities by URI rather than storing their attributes itself.

That migration is functionally complete and shipped — the eolas-destined predicates in media_api carry eolas URIs, the one-off migration machinery has been removed, and the reconciliation/webhook sync is in place. However, **`lucos_eolas` had no `docs/adr/` and no document recording what it now *is*** — its data model, its role as canonical home, its API contract, or the cross-service reconciliation contract that `lucos_media_metadata_api` and `lucos_arachne` depend on. This ADR records the as-built shape so that the contract is durable and reviewable, and establishes the `docs/adr/` convention in this repo.

This ADR documents the **settled** state. It does **not** decide the one open boundary question (Artist↔Person canonical source), which is tracked separately — see Scope.

## Decision

### 1. Canonical home

`lucos_eolas` is the **single canonical home for cross-domain entities** — encyclopedic facts that are not specific to any one consuming domain. Other services reference these entities by their eolas URI; they do not re-mint or re-store the entities' attributes.

### 2. Data model

All domain entities subclass an abstract `EolasModel` base (`metadata/models.py`), which provides a consistent RDF-native shape:

- `name` → `skos:prefLabel` (the canonical name).
- `alternate_names` → `rdfs:label` (also-known-as; **not** lookup keys — see `CLAUDE.md`).
- `wikipedia_slug` → `owl:sameAs` to the corresponding DBpedia resource.
- Each entity declares a **category** (a `Category` `TextChoices` enum carrying display-colour metadata), emitted as `eolas:hasCategory`.
- `get_rdf()`, `to_json()`, `get_absolute_url()`, and `get_webhook_url()` give every type uniform RDF/JSON serialisation and URI behaviour for free.

The store currently holds ~23 entity types across categories including PEOPLE (`foaf:Person`), ADVISORY (`eolas:Offence`), TEMPORAL (festivals, calendars, months), HISTORICAL (`eolas:Memory`, `eolas:HistoricalEvent`), and others. New types are added as `EolasModel` subclasses; this is expected to continue.

### 3. URI minting

Entity URIs are minted as `{APP_ORIGIN}/metadata/{model_name}/{pk}/` (`EolasModel.get_absolute_url()`), where `model_name` is the Django lowercased model name and `pk` is the database key (an integer for most types; an ISO code for `Language`/`LanguageFamily`). A small number of types override this to point at an external canonical authority (e.g. `LanguageFamily` uses the Library of Congress ISO 639-5 URI), but always expose an eolas-hosted `get_webhook_url()` so reconciliation events stay on the eolas origin.

### 4. API contract (the surface other services depend on)

**Read** (all RDF endpoints are content-negotiated: Turtle / JSON-LD / RDF-XML / N-Triples):

| Path | Returns | Auth |
|---|---|---|
| `GET /metadata/<type>/list/` | JSON array of all items of a type | `@api_auth` |
| `GET /metadata/<type>/<pk>/data/` | single entity as RDF | `@api_auth` |
| `GET /metadata/all/data/` | bulk RDF export of the whole store + ontology | `@api_auth` |
| `GET /ontology` | the ontology graph (types, properties, categories) | none |
| `GET /metadata/categories.json` | category colour metadata | none |
| `GET /metadata/<type>/<pk>/` | content-negotiated entrypoint (303 → `/data/` for RDF, admin for HTML) | none |

**Write:**

| Path | Behaviour | Auth |
|---|---|---|
| `POST /api/metadata/<type>/` | Creates an entity from a JSON body (`name` required, plus whitelisted scalar/FK fields). Duplicate handling: a case-insensitive `name` match returns **409** with the existing `{id, name, uri}` **only when exactly one** match exists (`existing.count() == 1`); zero or multiple matches proceed to create. Success returns **201** with `{id, name, uri}`. | `@api_auth` |

`lucos_media_metadata_api` uses this write path through its `ResolveOrCreateEolasEntityByName(entityType, name)` resolver (`api/eolas.go`) to turn composer/producer (and similar) names into eolas Person URIs.

### 5. Reconciliation contract (the cross-service contract)

eolas is **push-notify + pull-canonical**. On every entity mutation it emits a Loganne event; consumers re-fetch the canonical representation from the event's `url` (the estate-wide re-fetch-from-source convention, `lucos_loganne#370`). eolas does **not** push entity payloads to consumers.

Events (`metadata/signals.py`, `metadata/admin.py`), all carrying `{type, humanReadable, url, itemType}`:

- `itemCreated` — on `post_save` with `created=True`.
- `itemUpdated` — on `post_save` otherwise.
- `itemDeleted` — on `post_delete`.
- `itemMerged` — on the admin merge action; additionally carries `sourceUri` and `targetUri`, and **suppresses** the corresponding `itemDeleted` (the delete signal is disconnected for the duration of the merge).

`url` (and `sourceUri`/`targetUri` on merge) are always eolas-origin URIs (`get_webhook_url()` for create/update/delete, `get_absolute_url()` for merge); `itemType` is the human-readable type name (`verbose_name.title()`).

**Identity federation** is expressed in RDF, not in event payloads:

- `eolas:preferredIdentifier` (declared `owl:AsymmetricProperty` in the ontology, `metadata/views.py`) links an eolas entity to a more-authoritative external identity (notably a `lucos_contacts` Person). `lucos_arachne` walks `owl:sameAs`/`preferredIdentifier` closures to find the terminal URI and federate identity — see `lucos_arachne#539`.
- `owl:sameAs` to DBpedia is emitted from `wikipedia_slug` (`metadata/fields.py`).

### 6. Relationship to `lucos_media_metadata_api`

Per **`lucos` ADR-0005** (media-ecosystem URI namespace), media services store **only their own URIs or eolas URIs** in persistent entity references — never `lucos_contacts` URIs directly. The contacts relationship is reached in two hops via `eolas:preferredIdentifier`, federated by arachne. media_api stores eolas URIs in its v3 `tag.uri` column, denormalises the name alongside, and refreshes that name on `itemUpdated`. This ADR is the eolas-side counterpart to `lucos` ADR-0005's media-side rule.

## Scope

This ADR records what eolas **is** and the contract it **already** offers. It deliberately does **not** settle the **Artist↔Person canonical-source boundary** — i.e. when a recording artist is also a person, whether the canonical identity is a media-minted `mo:MusicArtist` URI or an `eolas:Person`. That is an open architectural+product decision tracked in **`lucos_arachne#597`** (which needs lucas42's sign-off). **Albums (`mo:Record`) are media-only** — eolas has no album-like type, so there is no divergence and they are out of scope. Whatever `lucos_arachne#597` decides will be recorded back into this ADR's §6 as a clarifying amendment.

## Consequences

### Positive

- **One canonical home for cross-domain facts.** Composers, places, content-warnings etc. live once, are reusable by any consumer, and are no longer entangled with media-specific storage.
- **Uniform, RDF-native contract.** The `EolasModel` base means every type — present and future — exposes the same read/write/serialisation/reconciliation behaviour with no per-type bespoke work.
- **Clean federation boundary.** Identity linking lives in RDF (`preferredIdentifier`, `owl:sameAs`) and is resolved by arachne, so individual consumers don't each re-implement cross-system entity matching.
- **Settled, reviewable contract.** The reconciliation events and API surface that media_api and arachne depend on are now written down; this repo now has a `docs/adr/` for future decisions.

### Negative

- **eolas becomes a critical-path dependency for media writes.** media_api's composer/producer save path resolves-or-creates against eolas synchronously (`ResolveOrCreateEolasEntityByName`). An eolas outage degrades that media-save path. (A 2026-05-29 incident initially suspected this coupling; the verified cause was elsewhere — but the coupling is real and worth keeping in mind for future reliability work.)
- **Re-fetch-on-event puts read load on eolas.** Every consumer re-fetches canonical data on each Loganne event rather than receiving it in the payload. This is the deliberate estate convention (`lucos_loganne#370`) and keeps eolas authoritative, but it does mean event bursts translate into read bursts against eolas.
- **The Artist↔Person boundary remains unresolved** until `lucos_arachne#597` is decided, so for that one entity class the canonical-source story is not yet clean.

## Alternatives considered

- **Leave this metadata in `lucos_media_metadata_api`.** Rejected: the entities are not media-specific (people, places, content-warnings are referenced well beyond media), so housing them in a media service blocks reuse and conflates two concerns. This is precisely what the migration unwound.
- **Use `lucos_contacts` as the canonical home for people.** Rejected: contacts is a personal CRM (real people Luke knows), not an encyclopedic registry (which includes historical, fictional, and public figures). The two are bridged by `eolas:preferredIdentifier`, not merged.

## Follow-ups

- **`lucos_arachne#597`** — decide the Artist↔Person canonical-source boundary; amend §6/Scope of this ADR once decided.
