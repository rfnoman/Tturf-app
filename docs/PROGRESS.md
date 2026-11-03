# Progress

Updated by Claude Code at the end of each phase.

| Phase | Status | Date | Notes |
|---|---|---|---|
| 00 Foundation | **done** (auth flow pending Clerk keys) | 2026-11-03 | Monorepo, Django 6.1 + PostGIS, Clerk JWT auth + webhook, Next.js 16 shell, CI |
| 01 Accounts, sports, profiles | **done** | 2026-11-03 | Sports catalogue + proposals, player profiles, onboarding wizard, FIFA-style card, authenticated e2e |
| 02 Turfs & grounds | not started | | |
| 03 Bookings & cash payment | not started | | |
| 04 Matches, squads, joining | not started | | |
| 05 Scoreboard | not started | | |
| 06 Ratings, track record, discovery | not started | | |
| 07 Inventory & counter POS | not started | | |
| 08 Store, orders, delivery | not started | | |
| 09 Fitness layer & notifications+ | not started | | |
| 10 Online payments & ledger | not started | | |
| 11 Hardening, Bangla, launch | not started | | |

## Log
<!-- Per phase: what was built, deviations from the plan, known gaps, follow-ups. -->

### Phase 00 — Foundation (2026-11-03)

**Built**

- **Repo**: `git init`, `.gitignore`, `.editorconfig`, `.nvmrc` (24), root `README.md` with
  the full setup path and the Clerk environment-variable checklist.
- **Infrastructure**: `docker-compose.yml` with Postgres 17 + PostGIS 3.6 and Redis 8,
  named volumes and healthchecks.
- **Backend** (`backend/`, uv, Python 3.14): Django 6.1.2, DRF 3.18.3,
  drf-spectacular 0.30.0, psycopg 3.3.7, Celery 5.6.3.
  - `config/settings/{base,dev,test,prod}.py`; `django.contrib.gis`, PostGIS backend,
    `TIME_ZONE="Asia/Dhaka"`, `USE_TZ=True`, `LANGUAGES = en, bn`.
  - All configurable business rules from DOMAIN/DECISIONS are already constants in
    `base.py` (booking confirmation window, reliability deltas, rating weights,
    `TURF_DELIVERY_CUTOFF_HOURS`), so later phases have nothing hard-coded inline.
  - `apps/core`: `UUIDModel`/`TimeStampedModel`/`BaseModel`, `DefaultPagination`,
    `IsPlatformAdmin`, Dhaka time helpers, `GET /api/v1/health` (reports the PostGIS
    version), idempotent `manage.py seed_demo`, and a migration creating the `postgis`
    **and `btree_gist`** extensions — the latter is needed by Phase 03's booking
    exclusion constraint and is not created automatically.
  - `apps/accounts`: custom `User` (`clerk_id`, email, phone, names, `image_url`,
    `is_platform_admin`, `last_synced_at`) created **before the first migration**;
    `ClerkJWTAuthentication`; svix-verified `POST /api/v1/webhooks/clerk`;
    `GET /api/v1/me`; Django admin.
  - Celery app with beat, `debug_task`, empty `CELERY_BEAT_SCHEDULE`.
  - OpenAPI at `/api/v1/schema/`, Swagger at `/api/v1/docs/`, Redoc at `/api/v1/redoc/`,
    with a registered security scheme so the schema advertises bearer auth.
- **Frontend** (`frontend/`, Node 24): Next.js 16.4.4, React 19.3, Tailwind 4,
  shadcn/ui (radix-nova), next-intl 4.14, TanStack Query 5.105, openapi-fetch.
  - `src/proxy.ts` (Next 16's renamed middleware) running bare `clerkMiddleware()`;
    `(player)`, `(owner)`, `(admin)` layouts gate with `await auth.protect()`, and
    `(admin)` additionally checks `is_platform_admin` from the backend.
  - Cookie-based locale with `en.json` / `bn.json` (identical key sets, enforced by a
    unit test) and a header language switcher backed by a server action.
  - Typed API client with injected token source — `useApiClient()` in the browser,
    `getServerApiClient()` on the server — plus `npm run gen:api`.
  - Mobile-first layout shell, home page, placeholder pages per route group, Clerk
    sign-in/sign-up pages, and a `/me` debug page.
- **Tests**: 68 backend tests (pytest + factory_boy) covering the auth class against a
  locally generated RSA keypair and fake JWKS (expiry, leeway, `nbf`, wrong `iss`,
  unlisted `azp`, missing `azp`, wrong signer, tampered payload, `alg=none`, missing
  `kid`, pending session, JWKS caching, key rotation, network failure), webhook signature
  verification (valid, missing headers, wrong secret, tampered body, stale timestamp) and
  all three `user.*` handlers, services, permissions, health, and the schema/docs routes.
  8 Vitest unit tests (locale config, catalogue parity, API client token handling).
  Playwright configured with desktop + mobile projects and three smoke specs.
- **CI**: `.github/workflows/backend.yml` (PostGIS + Redis services, GDAL/GEOS install,
  ruff, format check, missing-migration check, `spectacular --fail-on-warn`, pytest on a
  fresh DB) and `frontend.yml` (Node 24, lint, format, typecheck, Vitest, build).

**Deviations from the phase file** — recorded as DECISIONS D12–D18:

- `src/proxy.ts` + resource-level `auth.protect()` instead of a middleware route matcher
  (D12): Next 16 renamed the file and Clerk deprecated `createRouteMatcher`.
- No `[locale]` URL segment; locale lives in a cookie (D13).
- `cacheComponents` disabled (D14).
- Hand-rolled PyJWT + JWKS rather than `clerk-backend-api` (D15).
- `imresamu/postgis` locally because `postgis/postgis` is amd64-only (D16).
- Django 6.1 over 5.2 LTS, verified against the whole stack (D17).
- `MAILERS` instead of the deprecated `EMAIL_*` settings (D18).
- Container ports moved to **55432 / 56379**: a native Postgres and Redis already occupy
  5432/6379 on the dev machine and silently shadowed the containers.
- Node 24 (Active LTS) rather than 22; the machine's Node 20 is past end-of-life, and
  Vitest 5 / jsdom 30 require ≥ 22.12.

**Verified**

- `docker compose up -d` → both services healthy; `migrate` applies cleanly on a fresh DB;
  `seed_demo` is idempotent; `pytest --create-db` green (PostGIS auto-created in the test
  DB); `ruff` clean; `spectacular --fail-on-warn` clean; Celery worker + beat boot and
  connect to Redis; `/api/v1/health` reports PostGIS 3.6; Swagger and Redoc render;
  `npm run gen:api` generates types from the live schema; frontend lint, typecheck, format
  and build all pass; Vitest green; the home page renders server-side with the full header.

**Known gaps / follow-ups**

- **Blocked on Clerk keys**: sign-up → `User` row, the `/me` page against a real session,
  and the Playwright smoke suite. The last one needs a Clerk Frontend API domain that
  actually resolves — a well-formed placeholder key is enough to *build*, but a real
  browser follows Clerk's handshake redirect and fails DNS. Nothing else is blocked.
- **CI has never run**: there is no git remote and `gh` is not authenticated. Every CI step
  was executed locally instead. Push to GitHub to light it up.
- D9 follow-ups: confirm whether +880 SMS is plan-blocked on a dev instance, and get the
  tier and per-message rate from Clerk support in writing.
- `frontend/e2e` is not wired into CI yet; it wants real Clerk test credentials
  (`@clerk/testing`) — a natural addition in Phase 01 once onboarding exists.
- Media uploads still use local `FileSystemStorage`; Phase 02 introduces the
  django-storages abstraction as its phase file requires.

### Phase 01 — Accounts, sports catalogue, player profiles (2026-11-03)

**Built**

- **`apps/sports`** — the admin-curated catalogue (DOMAIN §2):
  - `Attribute` (the four shared physical attributes), `Sport` (slug, icon, `met_value`,
    `positions`), `SportFormat` (`players_per_side`, plus a `capacity` property Phase 04
    turns into `Match.capacity`), `SportAttributeWeight`, `SportSkill`, `StatDefinition`,
    `SportProposal`.
  - Catalogue data lives in `apps/sports/catalogue.py` as plain dicts with one
    `sync_catalogue()`; the data migration `0002_seed_catalogue` and `seed_demo` both call
    it, so a fresh database is usable immediately and a catalogue edit needs no migration.
    Seeded: Football (5v5/7v7/9v9/11v11), Futsal, Cricket (box/nets/T20), Badminton
    (singles/doubles) — 11 formats, 20 skills, 25 stat definitions, 16 attribute weights,
    with the stat sets DOMAIN §7 names and `minutes_played` on every sport.
  - `SportProposal` state machine in `services.py`, one function per transition:
    `approve` (creates the sport, **inactive** until an admin adds its formats, skills and
    stats — it would otherwise reach onboarding empty), `merge`, `reject` (reason required).
    `unique_sport_slug` walks past collisions so approving "Kabaddi" twice cannot 500.
  - API: `GET /sports` (whole catalogue, unpaginated — one call feeds the wizard),
    `GET /sports/{slug}`, `GET /attributes`, `POST|GET /sport-proposals`, and
    `GET /admin/sport-proposals` with `approve` / `merge` / `reject` actions.
  - Django admin with inlines for every child model, plus the DOMAIN §2 actions, including
    an intermediate page for "merge into…".
- **`apps/players`** (new app — D19) — the profile (DOMAIN §3):
  - `PlayerProfile` (1:1 `User`), `PlayerSport` (positions, `is_verified`, `self_assessed`,
    `is_hidden`), `PlayerAttribute`, `PlayerSkill`, `PlayerSportRating` (overall,
    `is_provisional`, and the track-record counters Phase 06 will fill).
  - Services: `complete_onboarding`, `add_player_sport`, `remove_player_sport`,
    `set_player_attributes`, `set_player_skills`, `compute_overall`, `refresh_sport_rating`,
    `update_profile`. **Self-assessed values are capped at `SELF_ASSESSED_RATING_CAP` in
    the service**, not the serializer, so a seed command or Celery task gets the same
    guarantee. Removing a sport with history only hides it.
  - API: `GET|PATCH /me/profile`, `POST /me/onboarding`, `POST /me/sports`,
    `DELETE /me/sports/{slug}`, `GET /players/{id}`. The public serializer drops
    `date_of_birth`, `weight_kg` and `discoverable`, exposing a derived `age` instead.
- **`GET /api/v1/config`** (D20) — the configurable rules the UI needs.
- **Frontend**: four-step onboarding wizard; a reusable `PlayerSportCardView` (built for
  the Phase 04 match board, Phase 05 scorecards and Phase 06 search, so it takes only data
  and fetches nothing); profile page with one tab per sport; settings page (discoverable
  toggle, weight with its calorie note, re-assessment, add/remove sports); admin
  sport-proposal queue. 130 message keys in `en.json`/`bn.json` at parity, with the
  short high-traffic strings already in Bangla.
- **Tests**: 268 backend (up from 68), 17 Vitest, 15 Playwright across desktop and mobile.

**Verified in the browser** (Chrome DevTools, real Clerk session): a new account is forced
to `/onboarding`; sliders cap at 75 *read from `/api/v1/config`*; finishing lands on the
card (Football 56 / Badminton 52, both "Unverified"); settings persist; a direct
`/players/{id}` link resolves with `discoverable=false` and shows no owner-only action;
admin approve created an inactive "Kabaddi" with 0 formats/skills/stats and merge pointed
"Soccer" at Football; no console errors; no horizontal overflow at 390px; Bangla renders.

**Bugs found and fixed along the way**

- **Reserved `LogRecord` keys** — `extra={"created": ...}` and `extra={"name": ...}` make
  `logging` raise `KeyError: "Attempt to overwrite 'created' in LogRecord"`. Present in
  Phase 00's `sync_user_from_clerk` too, and invisible under the test settings (the root
  logger has no handlers and sits at WARNING, so `logger.info` returns before the record
  is built) — it crashed `seed_demo` instead. Guarded by `apps/core/tests/test_logging.py`,
  which ASTs every `extra={...}` in the codebase.
- **Nameless accounts** (D21) — Clerk session tokens carry no identity claims, confirmed
  against the live instance (`azp,exp,fva,iat,iss,nbf,sid,sts,sub,v`). Every account showed
  as "Player" until a webhook that local development never receives. Now backfilled once
  from Clerk's Backend API.
- **`me.common.yes` never resolved** — `getTranslations("me")` scopes every lookup, so
  `t("common.yes")` on `/me` looked for `me.common.yes`. A Phase 00 bug that only fired on
  the branch rendering an empty name. Guarded by `src/i18n/__tests__/message-usage.test.ts`,
  which statically resolves every literal `t("…")` against `en.json`.
- **Routers added trailing slashes**, unlike every Phase 00 URL. `SimpleRouter(trailing_slash=False)`.
- **`JSONField` generated `unknown`** in the OpenAPI schema, making `Sport.positions`
  unusable from TypeScript. Declared explicitly as `ListField(child=CharField())`.
- **An approved proposal said "Merged into X"** when it had *created* X.

**Deviations / notes**

- `apps/players` is a new app not in CLAUDE.md's repository layout (D19).
- `@clerk/testing` added as a dev dependency for authenticated e2e (D23) — the Phase 00
  follow-up, now done. `pillow` added for `PlayerProfile.photo`.
- `next build` run against a live `next dev` server leaves the dev server serving stale
  output; restart it after a build.

**Known gaps / follow-ups**

- Catalogue strings (sport names, skill labels, positions) come from the database and are
  English in both locales. Phase 11 needs a translation strategy for them.
- `PlayerProfile.photo` uploads still use local `FileSystemStorage`; Phase 02 introduces
  django-storages as its phase file requires.
- The plural message `profile.sportCount` is an English template in `bn.json`, so Bangla
  reads "৩ sports". Phase 11.
- `SportProposal` creation is open to any authenticated user; Phase 02 narrows it to owners
  as the phase file says.
- e2e is still not wired into CI; it needs `CLERK_SECRET_KEY` as a repository secret.
