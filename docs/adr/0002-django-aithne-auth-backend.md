# ADR-0002: Django aithne auth backend (reference for lucos_eolas + lucos_contacts)

**Date:** 2026-06-24
**Status:** Accepted
**Discussion:** https://github.com/lucas42/lucos/issues/249

> **Amendment 2026-06-24 (#320, Option A — lucas42's decision):**
> (a) §4 clarified so `@require_scope` gates on `request.user.is_authenticated` **and** the
> scope (never the scope alone), and §5 maps a non-human principal to `AnonymousUser`
> **in production** — closing the §4 "valid token" ambiguity a security review raised (a
> verified agent JWT carrying a human-UI scope must not reach a protected view in prod).
> (b) Per lucas42, the dev-only `render-ui` path now reaches the **Django admin** of both
> services in development (a dev-only staff principal, GET-only, strictly inert in prod) — this
> revises the earlier "render-ui never reaches the admin" stance, for development only.
> (c) The model is deliberately left **open to a future, explicitly-granted production agent
> scope** (a planned human-approved data-suggestions capability) without weakening the human-UI
> protection. Option B (a hard `principal_class == "human"` reject at §3, dropping `render-ui`)
> was considered and not taken — `render-ui` is a wanted capability and Option A is
> security-sufficient.

## Context

`lucos_eolas` and `lucos_contacts` are the estate's two Django services that authenticate
**human sessions**. Both currently share the same pattern: a
`LucosAuthBackend.authenticate(request, token)` that GETs `AUTH_ORIGIN/data?token=<token>`
against `lucos_authentication` (token introspection), maps the returned id to a Django user,
and then calls `login(request, user)` to mint a long-lived Django server-side session
(`sessionid`). Redirect-to-login goes to `AUTH_ORIGIN/authenticate?redirect_uri=…`.

This is incompatible with `lucos_aithne`, the replacement auth service: aithne has **no
`/data?token=` introspection endpoint**. Per the aithne
[local-verification-contract](https://github.com/lucas42/lucos_aithne/blob/main/docs/local-verification-contract.md),
consumers verify a short-lived signed JWT **locally** against the JWKS at
`{AITHNE_ORIGIN}/.well-known/jwks.json` — there is no per-request callback.

This ADR records the **agreed design** for migrating both Django services off introspection
and onto aithne, so that the two migrations follow one known-good pattern rather than
diverging. `lucos_eolas` is the **reference implementation**; `lucos_contacts` follows the
same module, differing only where noted. It is the Django-specific instantiation of the
estate-wide
[consumer-migration-guide](https://github.com/lucas42/lucos_aithne/blob/main/docs/consumer-migration-guide.md);
the estate model itself lives in `lucos_aithne` ADR-0001 and is not re-decided here.

**This ADR is design only.** The code migrations are separate tracked work (see Follow-ups).

### Out of scope — the machine `@api_auth` path

Both services also expose a machine API authenticated via `Authorization: Bearer <key>` /
`?key=` against **lucos_creds** API keys (`getUserByKey` / `has_scope`), e.g. eolas's
`@api_auth` write path. That path does **not** use aithne and is **not** touched here — it is
the separately-parked M2M-convergence track. This ADR is the **human session** backend only,
matching the migration guide's scope.

## Decision

### 1. Verify the JWT per request; do **not** bridge to a long-lived Django session

The load-bearing decision: the `aithne_session` cookie JWT **is** the session, verified
locally on **every request**. We do **not** keep the old "introspect once → `login()` →
Django `sessionid`" model.

Why: an aithne session token is deliberately short-lived (15 minutes) and revocation is
eventually-consistent within that TTL (local-verification-contract, §"Token TTL"). If a
Django service bridged the first verified JWT into its own `login()` session — which defaults
to days — that session would **outlive the JWT and defeat the revocation model**: a revoked
grant would keep working until the Django session expired. So `request.user` is derived
**fresh from the JWT each request**; there is no `login()`/`sessionid` for authorisation.
JWKS-local ES256 verification is a cheap public-key operation (keys cached, off the hot path
once warm), so per-request is the right cost.

**Path (a), not path (b).** aithne supports two consumer shapes: (a) consume the domain-wide
`aithne_session` cookie and verify locally; (b) act as a full OIDC Relying Party doing its own
authorization-code flow. eolas and contacts are same-site under `l42.eu`, so aithne sets one
`aithne_session` cookie domain-wide (`Domain=l42.eu; Secure; HttpOnly; SameSite=None`) that
both services receive automatically. **Path (a) is chosen** (confirmed by lucas42 on
lucas42/lucos#249): it needs no per-service `client_secret`, no callback/code-exchange, and
keeps revocation honest. Path (b) and the off-the-shelf RP plugins it implies are evaluated
under Alternatives.

### 2. Mechanism — a populate-only authentication middleware

A custom Django authentication middleware replaces both the introspection
`AUTHENTICATION_BACKENDS` entry and the `login()` dance. Each request it:

1. defaults `request.user = AnonymousUser()`;
2. reads the token from the `aithne_session` **cookie** (the human-session source) or, if
   absent, an `Authorization: Bearer <aithne JWT>` header (the **aithne agent** source — see
   the note below);
3. verifies it (per §3); on success, maps the principal (per §5) and stashes the verified
   `scopes` on the request; on failure, leaves `AnonymousUser`.

**Two different "Bearer" tokens — do not conflate them.** The Bearer header read here carries
an **aithne** JWT (an agent's client-credentials token, same JWKS-verified format as the
cookie). It is distinct from the existing `@api_auth` machine path, which carries a
**lucos_creds** API key — that path is unchanged and out of scope (see "Out of scope" above).
The aithne agent Bearer source exists for one purpose in these two services: the **dev-only
`render-ui` snapshot path** (§4). An agent cannot receive the `Secure; Domain=l42.eu` cookie
on `http://localhost`, so Bearer is the only way `render-ui` can work for `lucos-ux` in
development. It grants nothing in production, where `render-ui` is ignored (§4) and no agent is
granted these services' human-UI scopes.

The middleware **never blocks** — it only populates `request.user`, exactly as Django's own
`AuthenticationMiddleware` does. This is deliberate and gives the `/_info` exemption for free:
because enforcement lives at the **view** (§4), not in a global blocking middleware, the
unauthenticated `/_info` endpoint simply carries no auth decorator and stays reachable. This
is the Django-idiomatic equivalent of the contract's "register public routes before the auth
middleware" rule — the "is this public?" decision lives in one place (the view/route table),
not in a middleware path allow-list that can drift out of sync (a security hazard called out
in the contract). `@login_required`, the Django admin, templates, and `request.user` all keep
working because they only require `request.user` to be populated.

### 3. The shared verifier (the contract both services implement)

A small `lucosauth/aithne.py` module, identical in both repos except the §5 mapping hook:

- **JWKS verification** via PyJWT + `PyJWKClient`, implementing local-verification-contract
  §1–6: ES256 with **algorithm pinning** (never trust the header `alg`); `iss ==
  {AITHNE_ORIGIN}`; `aud` contains `l42.eu`; `exp`/`iat` with 30-second leeway; require
  `exp`/`iat`/`sub`.
- **Accept both principal classes; stash the scopes.** The verifier accepts a recognised
  `principal_class` (`"human"` or `"agent"`) and rejects unknown classes — it does **not** hard-reject
  agents (that would be Option B). The verified `principal_class` and `scopes` are stashed on the
  request. This is what keeps the door open for a future production agent capability (§4): an agent
  token is verified and its scopes are available, even though — by default — an agent satisfies no
  human-UI check (§4/§5). Authorisation, not authentication, is where agent-vs-human capability is
  decided.
- **Serve-last-known-good on JWKS-fetch failure.** `PyJWKClient` (like `jose`'s client)
  **raises** on a failed JWKS fetch rather than serving stale — the library caveat the
  contract calls out explicitly. Without a wrapper, a JWKS blip during a cold start or a
  post-rotation unknown-`kid` refresh would reject **every** token across every consumer
  sharing that JWKS origin. The module retains the last successful key set and falls back to
  it on a fetch/connection error, rejecting a token only when its `kid` is genuinely absent
  after a refresh attempt — per the contract's resilience rule.
  - **Cold start fails closed — and must stay that way.** Serve-last-known-good can only fall
    back to a key set it already holds. On a cold start (empty cache) where the *first* JWKS
    fetch fails, there is no last-known-good, so verification **fails closed**: the token is
    rejected and the request is treated as unauthenticated (→ login redirect / 403). This is
    correct and deliberate. Implementers MUST NOT "fix" the empty-cache case by defaulting to
    an authenticated state or skipping verification — fail-closed is the only safe behaviour
    when keys are unavailable. (Operationally this window is bounded: a consumer only cold-starts
    on deploy/restart, and aithne's JWKS is the same origin the rest of the estate depends on.)
- **Quiet by default.** Per-token `jwt.decode` failures are expected noise (log at DEBUG);
  only JWKS-fetch failures log at WARNING, with `kid`/error strings control-char-sanitised
  before logging.

The cryptographically hard part is therefore an off-the-shelf, maintained library (PyJWT +
`cryptography`); only the thin glue (read cookie → decode → map → set `request.user`) is
ours.

### 4. Authorisation — the three-branch pattern

Protected views enforce via a small `@require_scope("…")` decorator (migration-guide C2, the
agreed estate-wide pattern):

1. **Authenticated human (`request.user.is_authenticated`) *and* required scope** → proceed.
2. **Authenticated human, missing/wrong scope** → the service's **own styled 403** (never
   redirect-to-login — the user is already signed in; re-login yields the same scopeless token
   and an infinite loop; there is no shared aithne "request access" endpoint).
3. **Not authenticated** — no token, an expired/invalid token, **or** a verified non-human
   token — → redirect to `{AITHNE_ORIGIN}/auth/login?next=<path>`.

**`@require_scope` gates on `request.user.is_authenticated` *first*, then the scope — never on
the scope alone (amended per #320).** This is the load-bearing disambiguation of what "valid
token" means in branch 1. **In production**, §5 maps every non-human (agent) principal to
`AnonymousUser` (whose `.is_authenticated` is `False`), so a verified **agent** JWT can never
satisfy branch 1 — *even if it carries a granted human-UI scope* — and falls to branch 3,
redirected exactly as an anonymous request is. This makes "no agent is granted these services'
human-UI scopes" a **redundant** belt-and-braces rather than a load-bearing operational
constraint: an accidental grant of `contacts:read` / `eolas:admin` / `contacts:admin` to an
agent does **not** open a production hole, because the agent never gets past the
`is_authenticated` gate. Two independent barriers — the §5 production mapping (agent →
`AnonymousUser`) and this decorator check — defense in depth, not a single point.
`is_authenticated` is idiomatic Django (exactly what `@login_required` checks), so composing
`@login_required` with the scope check yields barrier two for free. *(The dev-only `render-ui`
path is the one deliberate exception — see below — and is inert in production.)*

The `?next=` value is validated as an **internal path only**
(`url_has_allowed_host_and_scheme(allowed_hosts={request.get_host()})`, falling back to `/`)
to close the open-redirect risk the guide warns about.

**Dev-only `render-ui` — reaches scope-gated views *and* the Django admin (development only,
per lucas42's #320 decision).** In development, the `render-ui` escape hatch gives `lucos-ux`
(an agent, presenting its JWT via the Bearer source, §2) access to **both** services' rendered
surfaces, **including the Django admin pages**, for snapshotting. This is enforced in two
places, each strictly gated on `ENVIRONMENT == "development"`:

- the `@require_scope` decorator honours `render-ui` as a pass for scope-gated views
  (regardless of the specific scope); and
- §5 maps a dev `render-ui` agent to a **dev-only staff principal** (`is_staff` / `is_superuser`),
  which is what carries it through Django admin's own `is_staff` gate.

`render-ui` stays **GET-only** (contract §6): the dev staff principal is restricted to safe
methods (`GET` / `HEAD`) — enforced at the middleware layer so it also covers the Django admin
(mechanism in §5) — so it can render and snapshot admin pages but cannot POST mutations — an
agent can screenshot the delete form, not submit it. **In production the whole path is
inert**: with `ENVIRONMENT != "development"` no dev staff principal is ever minted, `render-ui`
is ignored, and agents map to `AnonymousUser` (above). This deliberately revises the earlier
"`render-ui` never reaches the admin" stance — for **development only** — and rests on the
standing render-ui invariant: safe only while dev data is non-sensitive and dev credentials
cannot mint production sessions.

**Future consideration — a production agent scope is not foreclosed (#320).** This design
verifies agent tokens (§3) and keeps their scopes on the request; it only declines to let an
agent satisfy a **human-UI** check. A capability lucas42 has flagged for later — agents
submitting **data-change suggestions** that require human approval before touching production
data — would be authorised by a **dedicated agent-facing endpoint** that checks
`principal_class == "agent"` **and** a dedicated, explicitly-granted agent scope (e.g. a future
`eolas:suggest`), **not** the human `is_authenticated` gate and **never** a human-UI scope. So
an agent *can* be granted a named scope in production later, for that purpose, without weakening
the human-UI protection above. The feature is **not built here** (details TBD); the design
simply leaves the door open.

### 5. Login view and per-service mapping hook

The login view collapses to a single redirect with **no `?token=` handling** — the cookie is
set domain-wide by aithne, so on return the middleware just picks it up.

**`map_principal` MUST branch on `principal_class` first.** The claim is `"human"` or
`"agent"` (contract §5), and `sub` means different things for each: a `lucos_contacts`
contact-id for humans, a `lucos_agent` persona slug for agents. So the human-mapping logic
below must run **only** for `principal_class == "human"` — running contacts' `sub → Person`
lookup on an agent slug would error (no `Person` with that id). For `principal_class ==
"agent"`, the mapping is **environment-aware**:

- **Production (and dev without `render-ui`):** do **not** resolve a Django user — `request.user`
  is left as **`AnonymousUser`** (the verified `scopes` stay stashed on the request, available to
  a future dedicated agent endpoint — §4). This is barrier two of the §4 defense-in-depth:
  `AnonymousUser.is_authenticated` is `False`, so `@require_scope` rejects the agent regardless of
  its scopes. In production an agent must **never** be mapped to a real or auto-created `User` —
  that would defeat the barrier.
- **Development *with* `render-ui`** (strictly `ENVIRONMENT == "development"`): map to a
  **dev-only staff principal** (`is_staff` / `is_superuser`) so `lucos-ux` can snapshot the
  scope-gated views and the Django admin (§4). This principal is minted **only** in development
  — never when `ENVIRONMENT != "development"`. Tag it at mapping time (e.g. a
  `request.render_ui_readonly` flag).
  - **GET/HEAD-only is enforced at the middleware layer, never in `@require_scope`.** Reject any
    non-`GET`/`HEAD` request carrying this principal with **`405`, before view dispatch**. It
    MUST sit at the middleware layer because it has to cover the **Django admin**, which does not
    pass through `@require_scope` — a method check placed only in the decorator would leave admin
    POSTs reachable, defeating the read-only intent. To preserve the populate-only auth
    middleware's "never blocks" property (§2), implement this as a **separate, development-only
    enforcement step** (its own small middleware, or an explicitly dev-gated block) rather than
    folding blocking logic into the populate step; it is naturally inert in production, where the
    dev staff principal is never minted. This restriction is **as security-critical as the env
    gate** and must be tested — e.g. a dev `render-ui` POST to an admin change view returns `405`.

Reject any unrecognised `principal_class`. The human mapping, then, is the only per-service
difference:

- **eolas (reference):** `User.objects.get_or_create(id=sub)`.
- **contacts (follows):** `sub` → `Person` → `get_or_create(LucosUser)` (plus the existing
  shadow `auth.User` so `django_admin_log` doesn't error), non-prod auto-create of the
  `Person`. The navbar username is **unaffected**: `templates/navbar.html` renders
  `user.get_short_name()` → `agent.getName()`, which reads the name from the local `Person`
  record, not from the JWT. `AnonymousUser` appears only when there is no valid session — i.e.
  precisely when there is no name to show and the user is being redirected to login.

### 6. Staff/superuser from a scope, not a hardcoded id

Both services currently hardcode admin rights to a single id (`id == "2"` in eolas;
`agent.id == 2` in contacts' `is_staff()`). This ADR replaces that with a **scope-derived**
`is_staff`/`is_superuser`, computed in `map_principal` from the verified `scopes` claim. This
aligns with `lucos_aithne` ADR-0001 §6 (capability comes from a granted, named scope, not from
identity): admin becomes grant-driven, auditable (granted via aithne `/admin/grants`),
multi-admin, and revocable, with no code change to add or remove an admin.

**Scope grain (answering the per-service difference, lucas42 on lucas42/lucos#249).** eolas's
only human surface **is** the Django admin; contacts has a **readonly browse layer** *and* the
Django admin. So:

| Service | Human surface | Required scope | Drives |
|---|---|---|---|
| eolas | Django admin (only surface) | **`eolas:admin`** | `is_staff` = `is_superuser` |
| contacts | readonly browse layer | **`contacts:read`** | view access (three-branch §4) |
| contacts | Django admin | **`contacts:admin`** | `is_staff` = `is_superuser` |

One admin scope grants both `is_staff` and `is_superuser` (matching today's all-or-nothing
admin); a finer staff-vs-superuser split can be added later if a real need appears — not now
(proportionate to a single-admin system).

**Vocabulary delta (dependency).** The current `lucos_auth_scopes` vocabulary holds
`eolas:read`/`eolas:write` (the **machine-API** scopes — different principal, retained) and a
single `contacts:use`, but **no human-admin scope**. This design needs `eolas:admin`,
`contacts:read`, and `contacts:admin` added (and `contacts:use`, which conflates read+edit,
retired in their favour). Because the holistic vocab pass (lucas42/lucos_auth_scopes#19) has
already closed, this is a **new vocabulary PR** requiring lucas42's approval per ADR-0001 §7,
and — being build-time coupled — an aithne (and creds) rebuild/redeploy before any token can
carry the scopes. It is a hard prerequisite of both code migrations. Tracked as a follow-up.

### 7. CSRF

The `aithne_session` cookie is `SameSite=None`, so it is sent on cross-origin requests;
cookie-authenticated writes therefore need CSRF mitigation (contract §"CSRF protection
required"). Both services already run Django's `CsrfViewMiddleware`, which protects human
cookie-auth POSTs (token + `Origin`/`Referer` checks) — so this regression is **already
covered**; the migration must simply confirm the middleware stays enabled on the migrated
views. The machine `@api_auth` views are correctly `@csrf_exempt` (Bearer-authenticated, not
cookie).

### 8. Configuration

Replace `AUTH_ORIGIN`/`AUTH_DOMAIN` with **`AITHNE_ORIGIN`** (deriving the JWKS URL, issuer,
and audience from it), per-environment — dev points at the **dev** aithne, since the prod
`Secure` `.l42.eu` cookie never reaches `http://localhost`. Drop the `AUTHENTICATION_BACKENDS`
introspection entry; register the new middleware after `AuthenticationMiddleware`.

## Consequences

### Positive

- **One known-good Django pattern.** Both migrations share `lucosauth/aithne.py`, the
  middleware, the three-branch decorator, and the login view; only the `map_principal` hook
  and the scope grain differ. Divergence risk is minimised, as the ticket asked.
- **Revocation stays honest.** No bridged session means `request.user.is_authenticated`
  reflects the JWT's current validity every request; a revoked grant stops working within the
  15-minute TTL.
- **Admin is grant-driven and auditable.** The magic `id == 2` constant is gone from both
  services; admin rights are granted, attributable, multi-admin, and revocable.
- **The crypto is off-the-shelf.** PyJWT + `cryptography` do the JWS/JWKS work; we own only
  thin glue.
- **An accidental agent scope-grant is not a production hole.** In production the §4
  `is_authenticated` gate plus the §5 agent→`AnonymousUser` mapping mean a verified agent JWT can
  never satisfy a protected view, even if it is wrongly granted a human-UI scope — two
  independent barriers (#320).
- **Door left open for a future prod agent capability.** Agents are verified and their scopes
  retained, so the planned human-approved data-suggestions feature can later authorise an agent
  on a dedicated scope without reworking the model or weakening human-UI protection (#320).

### Negative

- **A verification per request.** Cheaper than the old per-request `/data` introspection
  callback (local public-key verify vs network round-trip), but not zero. Acceptable, and a
  net improvement on today.
- **The dev `render-ui` path now mints a dev-only staff principal.** Allowing render-ui to reach
  the Django admin in development is a wider dev surface than before (admin snapshots, not just
  scope-gated views). It is strictly `ENVIRONMENT == "development"`-gated and `GET`/`HEAD`-only,
  and inert in production — but it widens what a dev `render-ui` token can see, and its safety
  rests on the standing invariant that dev data is non-sensitive and dev credentials cannot mint
  production sessions. A bug that let this principal be minted outside development would be a
  privilege escalation, so the environment gate is security-critical and must be covered by tests.
- **Enforcement discipline moves to the views.** With no `login()` gate, every protected view
  must apply `@login_required` / `@require_scope`; a view that forgets is silently public.
  This is the same exposure as today, but worth stating — it relies on convention, and unit
  tests rarely catch a missing decorator.
- **A new build-time-coupled vocabulary dependency.** Neither migration can complete until
  `eolas:admin` / `contacts:read` / `contacts:admin` exist in `lucos_auth_scopes` and aithne
  is redeployed. This serialises the work behind a lucas42-approved vocab PR.
- **The serve-last-known-good wrapper is bespoke care.** PyJWT's raise-on-fetch-failure means
  the resilience behaviour must be written and tested deliberately; getting it wrong
  re-introduces a shared single point of failure.

## Alternatives considered

- **An off-the-shelf OIDC login plugin** (`mozilla-django-oidc`, `django-allauth`,
  `social-auth-app-django`). aithne is a standards-compliant OIDC OP, so these *can* integrate
  via discovery. **Rejected for these two services** because they all implement aithne's
  *path (b)*: each Django service becomes its own OIDC RP with a `client_id`/`client_secret`,
  a `/callback`, code exchange, and a **bridged `login()` session** — which re-introduces the
  §1 revocation-staleness problem (unless further configured down, e.g.
  `mozilla-django-oidc`'s `SessionRefresh`, fighting the library's grain), and adds a
  per-service secret to provision and rotate. They earn their keep for **off-domain or
  third-party** software that cannot share the `l42.eu` cookie — not for same-site services
  the shared-cookie design was built to make cheap. Note the hard part (JWKS/ES256) is PyJWT
  either way, which those plugins themselves wrap. If consistency with future off-domain RPs
  later outweighs this, `mozilla-django-oidc` is the one to adopt.
- **Bridge to a short-lived Django session** (verify once, `login()`, set
  `SESSION_COOKIE_AGE` ≈ 15 min). Rejected: it still drifts from the JWT's actual validity,
  needs a refresh mechanism to stay aligned, and buys nothing over per-request verification,
  which is already cheap.
- **Reuse `eolas:write` for the human admin** instead of adding `eolas:admin`. Rejected:
  `eolas:write` gates the machine API (a different principal and surface); conflating the
  human Django superuser with the machine write-API scope muddies both audit and least
  privilege.

## Follow-ups

- **Vocabulary PR** on `lucas42/lucos_auth_scopes` — add `eolas:admin`, `contacts:read`,
  `contacts:admin`; retire `contacts:use`. Build-time coupled (aithne + creds rebuild/redeploy);
  needs lucas42's approval (ADR-0001 §7). Hard prerequisite of both migrations.
- **eolas migration** — implement this pattern in `lucos_eolas` (reference); part of the
  aithne consumer-migration waves (`lucas42/lucos_aithne#12`).
- **contacts migration** — port the pattern to `lucos_contacts`, changing only
  `map_principal` and the scope grain (§5, §6).
