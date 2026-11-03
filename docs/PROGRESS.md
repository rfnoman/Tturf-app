# Progress

Updated by Claude Code at the end of each phase.

| Phase | Status | Date | Notes |
|---|---|---|---|
| 00 Foundation | **done** (auth flow pending Clerk keys) | 2026-11-03 | Monorepo, Django 6.1 + PostGIS, Clerk JWT auth + webhook, Next.js 16 shell, CI |
| 01 Accounts, sports, profiles | not started | | |
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
