# Progress

Updated by Claude Code at the end of each phase.

| Phase | Status | Date | Notes |
|---|---|---|---|
| 00 Foundation | **done** (auth flow pending Clerk keys) | 2026-11-03 | Monorepo, Django 6.1 + PostGIS, Clerk JWT auth + webhook, Next.js 16 shell, CI |
| 01 Accounts, sports, profiles | **done** | 2026-11-03 | Sports catalogue + proposals, player profiles, onboarding wizard, FIFA-style card, authenticated e2e |
| 02 Turfs & grounds | **done** | 2026-11-03 | Turfs, grounds, hours, prices, PostGIS discovery, Leaflet maps, admin review, staff |
| 03 Bookings & cash payment | **done** | 2026-11-03 | Exclusion-constraint bookings, state machine, cash payments, reliability, Celery jobs, notifications |
| 04 Matches, squads, joining | **done** | 2026-11-03 | Matches per booking, squads, join requests, the D1 invite chain, match board with filters |
| 05 Scoreboard | **done** | 2026-11-03 | Teams + auto-balance, scorecard state machine, per-sport validators, disputes, MOTM, peer ratings, public shareable card |
| 06 Ratings, track record, discovery | **done** | 2026-11-03 | Pure versioned rating engine, rating history with explanations, track record, conduct reports, fair play, leaderboards, player search |
| 07 Inventory & counter POS | **done** | 2026-11-04 | Product catalogue, stock ledger, counter POS, rentals, low-stock alerts, warehouse |
| 08 Store, orders, delivery | **done** | 2026-11-04 | Match-aware store, cart split by source, fulfilment matrix with the 16h cutoff, orders, riders, cash on delivery |
| 09 Fitness layer & notifications+ | **done** | 2026-11-04 | Activity from matches, goals, streaks, bundles, reminder jobs, web push, SSE live updates, home dashboard |
| 10 Online payments & ledger | **done** (sandbox credentials pending) | 2026-11-04 | Provider abstraction, SSLCommerz with server-side validation, advances, policy refunds, balanced ledger, commissions, payouts |
| 11 Hardening, Bangla, launch | **done** (not deployed; see gaps) | 2026-11-04 | Audit; Bangla; PWA; performance; security; observability; admin tools; policies; deployable; launch journeys |

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

### Phase 02 — Turfs, grounds, pricing, discovery (2026-11-03)

**Built**

- **`apps/turfs`** (DOMAIN §1, §4):
  - `Turf` (PostGIS `PointField` with `geography=True`, so distances come back in metres
    on the sphere rather than degrees), `TurfPhoto`, `TurfMembership`, `Ground`,
    `OperatingHours`, `Closure`, `PriceRule`, and a seeded `Amenity` list.
  - `Turf.status` and `TurfMembership.status` are state machines with one service
    function per transition. `submit_turf_for_review` refuses a turf that is not actually
    reviewable — no grounds, no hours, or a ground with unpriced open hours — so an admin
    never opens an empty queue item and the owner hears about it first.
  - `TurfMembership` carries a **partial** uniqueness constraint (`status != removed`),
    so a person who leaves and is invited back does not collide with their own history.
- **Availability** (`apps/turfs/availability.py`) — the selector Phase 03 books against:
  - `operating hours − closures − active bookings`, sliced by the ground's `slot_minutes`,
    computed in Dhaka local time and returned as aware UTC.
  - **Closing after midnight works** (D27): a date's availability includes both that
    day's window and the tail of the previous day's, so Mirpur's 07:00–02:00 produces
    bookable 00:00 and 01:00 slots. Price coverage follows the same rule.
  - Unavailable slots are returned with a `reason` rather than omitted, so the UI greys
    them out instead of leaving a gap that reads as "closed".
  - Partial slots at closing time are not offered — a 90-minute slot cannot start at
    21:00 when the turf shuts at 22:00.
  - Bookings reach it through a **provider registry** (D25), so Phase 03 plugs in without
    touching this file.
- **Pricing**: most-specific rule wins, and a slot is priced by the band it *starts* in
  (D26). `activate_ground` refuses until every open minute is priced, and the 400 names
  the gaps — which is also what makes the seed a real test of the demo price tables.
- **Discovery**: `GET /turfs?near=lat,lng&radius_km=&sport=&area=&q=`, distance-annotated
  and nearest-first; alphabetical without a point, so declining geolocation still works.
  `near` takes latitude first (how humans write it) and is converted to PostGIS order in
  exactly one place.
- **Permissions**: `IsTurfOwner`, `IsTurfStaff`, `IsTurfOwnerOrStaffReadOnly` — all
  resolved through a live `TurfMembership` at *that* turf, which is what stops staff at
  turf A from touching turf B.
- **Frontend**: player discovery (filters, list/map toggle, opt-in "near me"), turf detail
  with a ground/date picker and the slot grid, owner dashboard, three-step registration
  with a draggable map pin, a management page for grounds/hours/prices/staff/submit, and
  the admin review queue. Leaflet via `next/dynamic` with `ssr: false` (D24).
- **Seed**: five approved Dhaka turfs (Dhanmondi, Mirpur, Banani, Uttara, Bashundhara),
  9 grounds, 28 price rules at real BDT rates, built **through the services** so a broken
  demo price table fails the seed rather than producing unbookable slots. Weekend peak
  pricing is Friday/Saturday, as it is in Dhaka — not Saturday/Sunday.
- **Tests**: 417 backend (135 in `apps/turfs`), 17 Vitest, 31 Playwright across desktop
  and mobile.

**Verified in the browser** (Chrome DevTools, real Clerk session): the five seeded turfs
list with sports and "from" prices; the map renders OSM tiles with a pin per turf;
Mirpur's detail page shows 00:00 and 01:00 slots from its 07:00–02:00 hours, and switching
to the 90-minute pitch reprices to ৳3200 and clears the selection. Then the whole
acceptance path: registered "Gulshan Sports Arena" with a map pin → draft; set hours;
added a ground; **activation refused**, naming every unpriced hour; added two price rules;
activated; submitted; confirmed it 404s for players; approved it in the admin queue; and
it then appeared publicly with the correct ৳2800 peak price. No console errors.

**Bugs found and fixed along the way**

- **Leaflet 500'd every page that imported it.** It reads `window` at module scope, and
  `"use client"` does not stop Next evaluating the module on the server for the initial
  HTML. Now behind `next/dynamic` with `ssr: false` (D24). Caught in the browser — the
  build passes, because these routes are dynamic and never prerendered.
- **Owners could not see their own inactive grounds** (D28). `turfs_for_staff` reused the
  public prefetch, which filters to `is_active=True` — hiding the one row an owner has to
  price and activate. The API tests had only ever built active grounds; three regression
  tests now cover player, owner and admin.
- **Leaflet's default marker was a broken image** ("Marker" alt text): its PNG is resolved
  relative to Leaflet's own CSS and no bundler rewrites it. Replaced with an inline-SVG
  `divIcon`.
- **`SerializerMethodField` generated `unknown`** in the OpenAPI schema, so `turf.sports`
  and `distance_km` were unusable from TypeScript. Annotated with `@extend_schema_field`.
  `GroundSerializer` is now declared response-only, which makes its model-default fields
  *required* in the generated response type instead of `number | undefined`.
- **The price-rule serializer rejected equal start/end times**, which is the documented
  "all day" idiom the model itself relies on.
- **`/turfs` collided** between the Phase 00 owner placeholder and the new player
  discovery page; the owner area moved to `/owner`.
- **e2e against the dev server was ambiguous**: Next's Dev Tools button is labelled
  "Open Next.js Dev Tools", so `getByRole("button", {name: "Next"})` matched it too.
  Selectors are now exact, and the suite runs against the production build as
  `playwright.config.ts` always intended.

**Deviations / notes**

- Leaflet + react-leaflet added as dependencies (D24). `react-leaflet` is installed but
  unused — the map is driven through Leaflet directly; it can be dropped in Phase 11.
- Nested owner routes are spelled out in `urls.py` rather than pulling in a nested-router
  package: one shape, five resources, no new dependency.
- `TurfPhoto` upload works but the owner UI does not expose it yet; media still uses
  local `FileSystemStorage`. The django-storages abstraction the phase file asks for is
  **not** done — see below.

**Known gaps / follow-ups**

- **django-storages is not wired up.** `TurfPhoto.image` and `PlayerProfile.photo` still
  write to local `FileSystemStorage`. `STORAGES` in `settings/base.py` is the single place
  that changes; do it before any deploy (Phase 11 at the latest).
- No photo upload UI on the owner page, and no closure editor — both have working API
  endpoints, so these are frontend-only gaps.
- Catalogue and amenity labels come from the database and are English in both locales,
  like the sports catalogue. Phase 11 needs one strategy for all of them.
- e2e still is not in CI; it needs `CLERK_SECRET_KEY` as a repository secret.

### Phase 03 — Bookings and cash payment (2026-11-03)

**Built**

- **`apps/bookings`** (DOMAIN §5, DECISIONS D3):
  - `Booking` on a `DateTimeRangeField` with a Postgres **`ExclusionConstraint`** —
    `ground WITH =, time_range WITH &&`, scoped to the statuses that hold a slot (D29).
    Double booking is impossible *at the database level*, not merely unlikely.
  - The state machine, one service per transition, each writing a `BookingEvent`:
    `reserved → confirmed → paid → completed`, plus `expired`, `cancelled` and
    `no_show`. Nothing else assigns `status`.
  - **D3 applied**: a player with ≥3 completed bookings and reliability ≥80, at a turf
    that allows it, is confirmed instantly; everyone else is held until
    `min(now + 2h, start − 1h)` — a slot released *after* kickoff helps nobody.
  - The price is re-derived from `get_availability`, never taken from the client, so a
    booking can only be made for a slot the turf offers at the price it advertised.
  - `mark_no_show` waits out `BOOKING_NO_SHOW_GRACE_MINUTES`: a player stuck in Dhaka
    traffic three minutes away is not a no-show.
  - Celery beat: reservation expiry every minute, completion every five.
- **`apps/payments`**: `Payment` with cash now and the shape Phase 10's providers and
  ledger need (D30). `record_cash_payment` is idempotent — a cashier double-tapping
  "mark paid" on a slow connection must not produce two rows.
- **`apps/notifications`** (DOMAIN §11): `Notification` + `notify()`, rendered once at
  creation from a template table (D31). Email goes out through `transaction.on_commit`,
  so nobody is emailed about a transition that then rolled back, and delivery failure
  never breaks the caller.
- **Phase 02's seam used as designed**: `BookingsConfig.ready()` registers a booked-range
  provider, so `apps/turfs/availability.py` needed **no change at all** and a booked slot
  immediately reads as taken.
- **Frontend**: booking review step (visibility, format, cash note, cancellation policy)
  on the slot grid; booking page with its status timeline and role-aware actions; my
  bookings split upcoming/past; the owner day calendar with the confirmation queue,
  inline confirm / mark-paid / no-show and a walk-in form; a polling notification bell
  and a notifications page.
- **Tests**: 562 backend (84 in `apps/bookings`, 24 in `apps/notifications`), 17 Vitest,
  43 Playwright across desktop and mobile.

**The concurrency test the phase asked for**

`apps/bookings/tests/test_concurrency.py` runs real threads against real connections
(`django_db(transaction=True)`), lined up on a `threading.Barrier`: two threads, then
ten, race for one slot and **exactly one wins** every time; the rest get `SlotTakenError`.
It also proves back-to-back slots do not collide (the range is half-open), that cancelling
frees a slot at once, and that the constraint is per ground rather than per turf.

**Verified in the browser** (Chrome DevTools, real Clerk session): booked a slot at
Dhanmondi Arena → `reserved` with "the turf has not confirmed yet", cash note and the
12h cancellation policy; the timeline recorded it. Took a walk-in for "Karim Uddin" at
the counter — the first attempt was correctly refused with "that slot has already
started", the second confirmed instantly and **Mark paid** moved it to `paid`. The booked
20:00 slot then showed as **BOOKED** on the player's availability grid, which is the
Phase 02 → Phase 03 seam working with no change to `apps/turfs`. No console errors.

**Bugs found and fixed along the way**

- **The exclusion constraint failed on a fresh database**: `uuid` has no default GiST
  operator class, so it needs `btree_gist`. The extension existed from Phase 00 but the
  bookings migration did not *depend* on it — it only worked because the dev database
  already had it. Caught by the first `--create-db` run.
- **Transactional tests wiped the seeded catalogue for the rest of the session.**
  `transaction=True` truncates tables, taking migration-seeded data with it;
  `serialized_rollback` does not help under `--reuse-db`. A module teardown now restores
  it explicitly.
- **`drf-spectacular` minted `Status4eaEnum`** for colliding `status` choice sets (D34).
- **`cancellation_free_hours` and `slot_minutes` read as `number | undefined`** on the
  client because model defaults make a serializer field optional; the response-only
  serializers now declare `read_only_fields = fields`.
- **The booking timeline rendered a time *range* for a single timestamp**
  (`09:07 PM–09:07 PM`); it now has its own `DhakaMoment` component.
- **A ground hosting several formats silently booked the first one**; the review step
  now asks when there is a choice.

**Deviations / notes**

- `Booking.squad_id` is a nullable UUID, not yet a FK — Phase 04 introduces `Squad` and
  replaces it, which is what the phase file asked for.
- The e2e walk-in spec asserts the *refusal* path (a draft turf takes no bookings) rather
  than the full counter flow: approving a turf needs a platform admin, which an
  unattended run cannot grant itself. The full flow is covered by backend tests and was
  driven by hand in the browser.
- `SlotGrid` buttons now carry `data-slot-start` / `data-slot-available`, a stable hook
  for tests and for Phase 04's deep links. Price and time text matched each other far
  too easily to select on.

**Known gaps / follow-ups**

- No reminder notifications yet (`BOOKING_REMINDER` has a template but nothing sends it)
  — Phase 09 owns reminders and web push.
- The owner calendar is a day list, not the day/week grid the phase file sketched. It
  carries every action, and a visual grid is cosmetic; worth revisiting in Phase 11.
- Cancelling a `paid` booking does not refund the cash payment — `refund_payment` exists
  and is tested, but nothing calls it. Phase 10 owns refunds.
- django-storages is still not wired up (carried from Phase 02).
- e2e still is not in CI; it needs `CLERK_SECRET_KEY` as a repository secret.

### Phase 04 — Matches, squads, join requests, match board (2026-11-03)

**Built**

- **`apps/matches`** (DOMAIN §6, DECISIONS D1 and D2):
  - `Squad`, `SquadMembership`, `SquadInvite`, `Match`, `MatchPlayer`, `JoinRequest`,
    `MatchInvite`. `Booking.squad` is now a real FK, replacing Phase 03's placeholder UUID.
  - **Every booking creates exactly one match**, through a hook registry on the booking
    lifecycle (D35) — `apps.bookings` still knows nothing about matches.
  - **Visibility is derived** from the booking plus the squad's `accepts_public_requests`
    (D36), and so is the organiser. Capacity is `players_per_side × 2` capped by the
    ground, so a 7v7 format on a ground that holds 10 is a 10-player match.
  - The **DECISIONS D1 chain** for a closed squad: a member *proposes*, the leader
    approves, then the player accepts. An invite from the organiser skips the proposal,
    because there is nobody left to ask. The proposed player is told nothing until the
    leader approves.
  - **Capacity is decided under a row lock** (D37). The losing request stays pending.
  - A player cannot be in two matches at once, checked on request *and* on accepting an
    invite.
  - Celery beat: requests and invites expire at match start, and statuses advance with
    the clock.
- **Match board**: `GET /matches/board` with sport, area, near/radius, date, time-of-day
  (filtered on the **Dhaka-local** hour, which is how a player thinks about "evenings"),
  spots-left and rating-band filters. Roster size, spots left and the roster's average
  rating are all computed in the database (D38).
- **Frontend**: the match board with every filter and a list/map toggle; the match page
  with the roster (linking to Phase 01 profile cards), the organiser's request queue with
  "also add to squad", the proposal queue, and invite/leave/remove; squad list, create
  form and squad page with the open/closed toggle; and the booking flow extended with
  group mode and a squad picker.
- **Tests**: 703 backend (122 in `apps/matches`), 17 Vitest, 59 Playwright.

**The test matrix the phase asked for**

`apps/matches/tests/test_visibility_matrix.py` asserts all four DOMAIN §6 shapes ×
four roles (outsider, squad member, leader, booker) across *see*, *request* and *invite*,
plus where each invitation starts in the chain. Writing it first caught my own
misunderstanding immediately: I had assumed an **open squad's match was visible only to
the squad**, when the flag controls who may *join*, not who may *look* — the board is
public by definition. The code was right; the matrix was wrong, and it is now documented
in the table.

`apps/matches/tests/test_capacity_race.py` contests the last spot with real threads on
real connections: two simultaneous approvals leave exactly one winner, and eight
simultaneous adds against four spots leave the roster at exactly four.

**Verified in the browser** (Chrome DevTools, real Clerk session): the board renders the
brief's shape — "Banani Sports Hub · Indoor Court · Wed 4 Nov 19:00 · 5v5 · Need 9 ·
Avg 64 · ৳2800". Filtering to badminton left the one badminton match; adding "spots ≥ 5"
correctly emptied the board, since that match is a 2-player singles. Asked to join a
match, and the form was replaced by "You have already asked to join". Then as the
organiser of another match: two requests with their messages, approved one, and the page
went 1/10 → 2/10, "Need 9" → "Need 8", queue down to one. Created an open squad through
the UI and confirmed the leader membership and the open/closed explanation. Notifications
fired to the right people throughout. No console errors.

**Deviations / notes**

- The board's map view centres on the player and the rows carry distances; it does not
  pin individual matches, because the board payload deliberately carries no coordinates.
  Phase 06's player/match search is the right place to revisit that.
- "Invite a player" offers the reader's squad-mates who are not already playing. Full
  player search is Phase 06, as the phase file says.
- `MatchPlayer.attended` exists and is unused until Phase 05 fills it from the scorecard.

**Known gaps / follow-ups**

- A squad has no crest upload yet (the field exists); and no squad-level match history
  page — Phase 06's track record is the natural home.
- The match page fetches each of the reader's squads to build the invite list, which is
  a handful of extra requests for somebody in many squads. Worth one endpoint when
  Phase 06 adds player search.
- django-storages is still not wired up (carried from Phase 02).
- e2e still is not in CI; it needs `CLERK_SECRET_KEY` as a repository secret.

### Phase 05 — Scoreboard, MOTM, peer ratings (2026-11-03)

**Built**

- **`apps/scoring`**: `MatchTeam` / `MatchTeamPlayer` (two sides per match, a captain
  each), `Scorecard` (1:1 with the match; `draft → submitted → confirmed → locked`, with
  `disputed` branching back to the scorer), `PlayerStat` (one row per player per
  `StatDefinition`, so a new sport needs no migration), `ScorecardEvent`, `MotmVote` and
  `PeerRating`. Self-votes and self-ratings are refused by **check constraints**, not only
  by the service.
- **Pluggable validators** (`apps/scoring/validators/`): a `@register(slug)` registry with
  a generic pass (bounds from the stat definitions, and every player on the roster) that
  runs **before** the sport-specific one, so an unknown sport is still validated. Football
  and futsal (goals ≤ team score, assists ≤ goals, clean sheet only at nil), cricket (runs
  and wickets reconcile with the totals), badminton (no draw, sets won ≤ the side's score).
  Failures come back grouped by field, which is what lets the entry form show each message
  against its own input.
- **Services**: `set_teams`, `auto_balance_teams` (greedy by current sport rating),
  `assign_scorer`, `save_draft` (deliberately *not* validated — a scorer filling in a phone
  form at the ground is never blocked halfway), `submit_scorecard`, `confirm_scorecard`,
  `dispute_scorecard`, `resolve_dispute`, `lock_scorecard`, `cast_motm_vote`,
  `close_motm_voting` (ties broken on positive-stat contribution), `submit_peer_ratings`.
- **Who may do what** comes from the API, never re-derived on the client: `can_edit`,
  `can_confirm`, `can_resolve`, `motm_voting_open`, `my_motm_vote`, `my_peer_ratings`.
  The opposing captain is resolved from the side the **scorer** played on, and either
  captain may confirm when the scorer did not play (turf staff).
- **Celery beat**: submitted cards auto-confirm after 24h (DOMAIN §7), MOTM voting closes
  on the same clock, and attendance is filled from the card.
- **Phase 05 → 06 seam**: `lock_scorecard` fires a `scorecard_locked` hook (the D25/D35
  registry pattern again) for the rating engine to consume. A failing hook logs and leaves
  the lock standing — the card is the record of what happened, whatever downstream does.
- **Frontend**: the team builder (tap-to-move, auto-balance, captains), mobile-first
  scorecard entry generated from the sport's stat definitions with big +/− steppers and
  inline per-field errors, the confirm/dispute card for the opposing captain, the same
  form in "resolve" mode for staff settling a dispute, the post-match sheet (one MOTM vote
  plus anonymous 1–5 ratings), the read-only card shared by the signed-in and public
  views, the **public shareable page** at `/scorecards/{matchId}` with a generated Open
  Graph image, and a "recent results" track record on both profile pages.
- **Tests**: 843 backend (119 in `apps/scoring`), 17 Vitest, 65 Playwright.

**Verified in the browser** (Chrome DevTools, real Clerk session): built the teams by
auto-balance, moved a player across, named both captains, then entered 1–3 with four goals
against a team that scored three — rejected inline with "Team B's players have 4 goals
between them, but the team scored 3", card still a draft. Corrected and submitted; voted
MOTM and saved star ratings (both re-render from the server on reload). As the opposing
captain: disputed with a reason; as the resolver: corrected the goal attribution and
locked it — "Verified by the turf", full history trail, and the public link appeared. The
public page opens signed-out, a card that is not locked 404s there, and the Open Graph
image renders the score. Checked the entry screen at 390px: steppers, teams and stars all
hold up. No console errors.

**Deviations / notes**

- **Live scoring (step 5b) was not built** — the phase file says not to without a
  confirmation, and there has been none.
- A disputed card is editable by its scorer *and* resolvable by staff. The page offers
  **resolving** first to anyone who can do both: settling the dispute is the action that
  ends it.
- Peer ratings are stored but change nothing yet; Phase 06 owns the rating engine.
- `metadataBase` is now set from `NEXT_PUBLIC_SITE_URL`, without which Next cannot build
  the absolute Open Graph image URL that Messenger and WhatsApp need.

**Two things the browser caught that the tests did not**

- The team builder seeded its state from props *once*, so auto-balance changed the
  database and nothing on screen. It now derives the saved sides every render and keeps
  only the unsaved moves in state.
- Validator messages rendered Decimals verbatim — "4.00 goals" reads like a rounding
  error. `number()` normalises them.

**Known gaps / follow-ups**

- The Open Graph image uses the bundled font only: a Bangla team name will not render
  until Phase 11 ships a font with it.
- MOTM closing after 24 hours is covered by tests and the beat schedule, not by a browser
  run — there is nothing to see for a day.
- django-storages is still not wired up (carried from Phase 02).
- e2e still is not in CI; it needs `CLERK_SECRET_KEY` as a repository secret.

### Phase 06 — Ratings engine, track record, discovery (2026-11-03)

**Built**

- **`apps/ratings/engine.py`** — pure, deterministic, no ORM. One locked match becomes a
  0–100 performance score from three parts: **stats** against per-sport benchmarks (capped
  at 1.5× so one lopsided scoreline cannot mint a 99), **result** shifted by how strong the
  opposition was, and **peer ratings** when there are any. The player's rating then moves a
  fraction of the way towards that score, scaled by `RATING_VERIFIED_SCORECARD_WEIGHT` for a
  card the turf stands behind, and clamped (±3 settled, ±6 provisional).
- **The weights are a table, not code** (`apps/ratings/weights.py`, `WEIGHTS_VERSION`), one
  per sport, mapping each stat to a benchmark, a weight and the skill it feeds. A sport with
  no table is still rated on result and peers — which is what keeps adding a sport a
  catalogue row rather than a release.
- **Two deliberate refusals in the engine**: a skill no stat speaks to is left exactly where
  it is (nudging dribbling towards the overall would make "why did it change?"
  unanswerable), and speed, agility and strength stay self-assessed because no stat in these
  sports says anything about them. Only stamina moves, and only when minutes were recorded.
- **`apply_locked_scorecard`** subscribes to Phase 05's `scorecard_locked` hook: it rates
  everybody who played, writes `PlayerSkill`/`PlayerAttribute` as `computed`, fills the
  `PlayerSportRating` counters, unlocks the sport, marks attendance, updates the track-record
  tables and stores a `RatingChange` with the engine's explanation **and its inputs**.
  Idempotent per `(player, match)`.
- **Replay** (`recompute_all`, `manage.py recompute_ratings [--player] [--sport] [--dry-run]`)
  re-runs the stored inputs rather than re-grading old matches against today's ratings
  (D45), so it lands on exactly the numbers the incremental updates produced.
- **Track record**: `PlayerSportStats` (career totals, stat totals and the last five
  results) and `PlayerGroundStats` (the same per ground — "3× MOTM at Mirpur").
- **Conduct and fair play**: `ConductReport` (roster players only, once per person per
  match, never yourself — enforced by check constraint as well as service), an admin review
  queue, and a fair-play score built **only** from things that happened: cards on locked
  cards and upheld reports.
- **Leaderboards**: a nightly Celery task writes `LeaderboardEntry` rows per sport, per
  turf and platform-wide, monthly and all-time, for highest rated, most MOTM, most wins and
  the sport's headline stat. Counted from `RatingChange`, which is what makes "this month at
  Mirpur" answerable at all.
- **Discovery**: `Availability` windows ("free Friday evening in Mirpur") and
  `GET /players/search` with sport, position, rating band, area, reliability, where they
  have played and when they are free — ranked by fit, not by rating alone, and respecting
  `discoverable` (which gates search only; a direct profile link still resolves).
- **Frontend**: the profile gained a fair-play badge, a track record with the form guide and
  per-ground rows, and a rating chart whose every point carries the engine's own words
  ("stats 62 · result 86 · verified by the turf · still finding your level"); a player
  search page with filters, invite-to-match and invite-to-squad through the Phase 04 chain;
  an "I'm free…" panel on the match board; leaderboards on the turf page; a conduct report
  form on the post-match page; and the admin review queue.
- **Tests**: 968 backend (100 in `apps/ratings`, 29 of them golden-value engine tests),
  17 Vitest, 73 Playwright.

**Verified in the browser** (Chrome DevTools, real Clerk session): locked the Phase 05 match
and the three players moved 56→62, 57→52 and 50→54, each with a breakdown that explains
itself. The profile shows the earned 62 with finishing up from the hat-trick, "1 played ·
1W 0D 0L", the ground row, and the chart entry. Searched players, filtered to an area with
nobody in it (empty state), then to Dhanmondi (18 results), and sent a squad invitation
through the existing chain. Posted an availability window and removed it. The turf page
shows "Highest rated" and "Top goals" for the month. Filed a conduct report from the
post-match page, upheld it in the admin queue, and watched the reported player's fair play
drop from 100 to 85. No console errors.

**Weights, for review**

The numbers are a first pass and are meant to be argued with — they live in one table and
`WEIGHTS_VERSION` exists so changing them is a deliberate, replayable act. Per match, a
"good return" benchmark and its weight:

| Sport | Stat → skill | Benchmark | Weight |
|---|---|---|---|
| Football | goals → finishing | 1 | 30 |
| | assists → passing | 1 | 20 |
| | saves → goalkeeping | 3 | 20 |
| | clean sheet → defending | 1 | 12 |
| | yellow / red | — | −5 / −15 off the score |
| Futsal | goals → finishing | 2 | 30 |
| | assists → passing | 2 | 20 |
| | saves → goalkeeping | 4 | 20 |
| Cricket | runs → batting | 30 | 30 |
| | wickets → bowling | 2 | 30 |
| | catches → fielding | 1 | 15 |
| Badminton | sets won → smash | 2 | 30 |
| | points won → net play | 40 | 25 |
| | aces → serve | 3 | 20 |
| | errors | 10 | −8 off the score |

Components: stats 0.45, result 0.35, peers 0.20 (renormalised when nobody rated the match);
a match with no notable stats still scores 40, not 0; MOTM is a flat +6.

**Deviations / notes**

- A player's self-assessment no longer overwrites an earned rating (D44): `refresh_sport_rating`
  stops writing `overall` once a match has been counted. Editing a skill slider used to undo
  every match the player had earned.
- The FIFA card now shows "Verified" and "Finding level" as two badges. They are two
  different facts — the sport is unlocked, the rating is still settling — and merging them
  read as though playing had achieved nothing.
- Near/distance ranking in player search is by area, not PostGIS: a profile has an area, not
  a point. Phase 11 can add a point if it proves worth asking for.

**One thing the browser caught that the tests did not**

Search results came back without their sport cards — `sport_cards` is attached by the
profile *view*, not the serializer, so a list had none. It is now a method field on the
search serializer, reading the relations `profile_queryset()` has already prefetched.

**Known gaps / follow-ups**

- Leaderboards are read from the nightly table, so a brand-new turf shows an empty board
  until 03:00. Worth a "computed overnight" line, which the empty state now says.
- Head-to-head records (DOMAIN §8) are not built; the per-ground table is the useful half
  and head-to-head needs a UI question answering first.
- django-storages is still not wired up (carried from Phase 02).
- e2e still is not in CI; it needs `CLERK_SECRET_KEY` as a repository secret.

### Phase 07 — Inventory, rentals and the counter (2026-11-04)

**Built**

- **`apps/inventory`** is shaped around one idea: **`StockItem` is a cache of
  `StockMovement`.** Every quantity change happens in a service, inside a transaction,
  with the row locked, and always alongside the movement that explains it. Views,
  serializers and the admin never touch `on_hand` or `reserved` — the admin's quantity
  fields are read-only and the movement log is append-only there too.
- **Models**: `ProductCategory` (seeded by migration), `Product` (platform- or
  turf-owned, sale or rental, nutrition panel, fitness tags, sport relevance, barcode),
  `StockLocation` (the warehouse, or a turf), `StockItem` (`on_hand`, `reserved`,
  per-location price override, low-stock threshold), `StockMovement`, `CounterSale` +
  `CounterSaleLine`, `Rental`.
- **Database-level guards**: stock and reservations cannot go negative, `reserved` can
  never exceed `on_hand`, a product's owner and turf must agree, and a location is either
  the warehouse or a turf. The services check the same things and raise a readable error
  first; the constraints are there for everything that is not a service.
- **Services**: `receive_stock`, `adjust_stock(reason)` (a reason is required — an
  unexplained adjustment is indistinguishable from a bug), `reserve` / `release` /
  `commit_sale` for the Phase 08 store, `record_counter_sale`, `void_counter_sale`,
  `rent_out`, `return_rental`, `mark_rental_lost`, and low-stock notifications to the
  turf's staff.
- **Rented gear stays `on_hand` and becomes `reserved`**: it is still the turf's and it
  is coming back, but it cannot be rented to two teams at once. Gear that never comes
  back leaves stock through an adjustment and keeps the deposit.
- **API**: a turf's own products and stock under `/me/turfs/{slug}/…` (owners write,
  cashiers sell), the counter, the rentals board, the platform warehouse for admins, and
  the public reads Phase 08 needs — `GET /turfs/{slug}/products` and `GET /store/products`.
  Out-of-stock answers **409**, not 400: nothing is wrong with the request, somebody else
  simply got there first.
- **Frontend**: the owner's inventory screen (shelf, inline receive and adjust, movement
  log, add-product form that shows nutrition only for food and drink), a tablet-friendly
  **counter POS** (category grid, tap-to-add, running total, cash received → change due,
  void), the rentals board, and the admin warehouse.
- **Seeds**: realistic Dhaka prices — water ৳25, electrolyte ৳70, banana ৳15, cha ৳20,
  bibs ৳150/match with a ৳500 deposit — stocked through `receive_stock` so even the demo
  database starts with a ledger that reconciles.
- **Tests**: 1051 backend (68 in `apps/inventory`), 17 Vitest, 81 Playwright.

**The two tests that matter**

`test_the_ledger_always_reconciles` does everything a turf can do to one product — sells,
adjusts, reserves, releases, commits, receives, rents out, takes back, writes one off —
then replays the movements and compares them with the cached columns. If a service ever
changes a quantity without writing its line, that test fails.

`test_concurrency.py` contests stock with real threads on real connections: three threads
reaching for the last two items leave exactly two reservations, ten threads against four
items leave four, and four cashiers selling the last bottle leave one sale and three
refusals. The ledger still reconciles afterwards.

**Verified in the browser** (Chrome DevTools, real Clerk session): rang up three waters at
Dhanmondi — ৳75 total, ৳25 change from ৳100 — and the shelf went 48 → 45 with the ledger
agreeing. Handed out a set of bibs (৳500 held, available 4 → 3) and took them back. Counted
the shelf down with "a crate went missing" as the reason, which logged the adjustment and
sent the owner a low-stock notification saying "3 left at Dhanmondi Arena". Checked the
warehouse screen and the POS at tablet width. No console errors.

**Deviations / notes**

- The counter caps each tap at what is on the shelf, so a cashier cannot ring up more than
  exists. The API refuses it anyway; finding out at "Take payment" is the wrong moment.
- A product is retired by deactivation, never deleted: past sales point at it.
- `Booking` now exposes `player_profile_id`. The staff screens act on a person — renting
  gear out, attaching a sale — and a name is not an identifier (D39).
- Two e2e helpers now pick the first ground that still has a free slot rather than the
  default one. Repeated local runs had booked a ground out for a day, which broke tests
  that were not about that at all.

**One trap removed**

Tests that run with `django_db(transaction=True)` truncate the migration-seeded tables, and
each such module had been re-seeding the catalogues it happened to know about. Adding
product categories made that fail everywhere at once. There is now one `conftest.py` that
re-seeds all of it around any transactional test, so the next one inherits the fix instead
of rediscovering it.

**Known gaps / follow-ups**

- `apps/bookings/tests/test_concurrency.py` flaked once in a full run under load (barrier
  timeout) and passed on its own and on every re-run. Worth watching; the barrier timeouts
  may need raising if it recurs in CI.
- Barcode scanning is a field on the product and a search path in the API, but the POS has
  no scanner input yet — it needs a device to test against.
- Rentals can be attached to a match or a booking, but the board only offers today's
  bookings; attaching to a match wants the Phase 04 match picker.
- django-storages is still not wired up, so product images are URLs rather than uploads.
- e2e still is not in CI; it needs `CLERK_SECRET_KEY` as a repository secret.

### Phase 08 — Store, orders and delivery (2026-11-04)

**Built**

- **`apps/store`** around two rules. **One order has one stock source**: a cart holding the
  platform's whey and a turf's bananas becomes two orders at checkout, because different
  people pick, carry and are paid for them. And **what a player may choose depends on where
  the goods are** — the DOMAIN §9 matrix, in one function.
- **`fulfilment_options`** answers with every option and, for the closed ones, the reason:
  turf stock is pickup only (D4); platform → a turf needs a match the player is actually on
  and more than `TURF_DELIVERY_CUTOFF_HOURS` before kick-off (D5, overridable per zone);
  platform → an address is priced by `DeliveryZone` and refused by name when nobody
  delivers there. Perishables are pickup only whatever else is true.
- **Checkout is all or nothing.** It reserves through the Phase 07 services, snapshots the
  name, price and nutrition onto each line, and rolls the whole thing back if the last item
  of the second order is gone — leaving the cart intact so the player can fix it.
- **The order lifecycle**: placed → accepted → packed → out for delivery | ready for pickup
  → delivered | picked up, plus cancelled. Settling commits the stock and records the cash
  as a `Payment` (which now targets a booking **or** an order, exclusively). Cancelling
  releases the stock. A player may cancel until it is packed; after that only the source can.
- **Riders** are a profile on an ordinary account, not a separate kind of user, and
  `rider_orders` only ever returns what they were given.
- **Celery**: a cutoff reminder to players whose match is about to pass the deadline ("Order
  by 5 AM"), sent once per match, and a warning to admins about turf deliveries that are not
  on their way with kick-off approaching.
- **Frontend**: the store leads with the player's next match and a live cutoff line, with a
  source switcher, category and fitness-tag filters and nutrition on the card; the cart is
  grouped by source with a fulfilment choice per group — unavailable options stay visible
  with the API's reason — and an address can be added without leaving it; order tracking
  with the timeline; the turf and platform queues (one component, since the job is the
  same); and a one-handed rider view with call and map links.
- **Tests**: 1143 backend (77 in `apps/store`), 17 Vitest, 89 Playwright.

**The matrix is tested as a matrix**

`test_fulfilment.py` walks each source × each option, checks that every refusal carries a
reason, and pins the cutoff at the exact boundary: a minute inside it works, a minute past
it does not, a zone may override it, and somebody else's match is refused by name. That is
the phase's acceptance line ("at 4:59 AM it works, at 5:01 AM it is disabled") as an
assertion.

**Verified in the browser** (Chrome DevTools, real Clerk session): with a match 28 hours out
the store led with "For your match at Mirpur Turf Club" and "28h left to have it sent to the
turf". Added a turf item and a platform item; the cart showed two groups, each with its own
options and reasons ("It is already at the turf — pick it up there", "The platform store
delivers; there is nothing to pick up"). Checkout produced two orders, both holding stock.
Moved the match inside the cutoff and the option became "Too late for this one — orders have
to be in 16 hours before kick-off", exactly as the acceptance list asks. Added a Dhanmondi
address from the cart and home delivery priced at ৳60, total ৳120. Then: accepted the order
in the admin queue, assigned a rider, marked it on the way and delivered from the rider
view — stock went 100 → 99 and a ৳120 cash payment was recorded. Picked up the turf order
from that turf's queue. No console errors.

**Deviations / notes**

- The platform warehouse offers no pickup: there is no counter to collect from, and saying
  so is better than a silently missing option.
- Settling is allowed straight from `placed`. A player who orders at the counter and takes
  it away should not need the staff to tap "accept" first; the event log still records it.
- `cancel_order` checks "is this order finished?" before the player/packed rule, so a
  delivered order says "already finished" rather than "call the turf".
- Delivery zones are matched by area name, with an optional PostGIS polygon that wins when
  both are present. A Dhaka address is a neighbourhood long before it is a coordinate.

**Known gaps / follow-ups**

- Riders are created in the admin; there is no sign-up flow for them.
- The match page does not yet show "items for this match" — the data is there
  (`Order.match`), it is a component away, and it belongs next to the Phase 05 scorecard
  work on that page.
- Delivery to a *turf* is not yet distinguished in the rider view from delivery to an
  address; the card shows the match instead of a street, which works but is not a route.
- django-storages is still not wired up, so product images are URLs.
- e2e still is not in CI; it needs `CLERK_SECRET_KEY` as a repository secret.

### Phase 09 — Fitness layer, reminders and live notifications (2026-11-04)

**Built**

- **`apps/fitness`**: `ActivityLog` (one per player per match, enforced by constraint),
  `FitnessGoal`, `Bundle` + `BundleItem`, `ReminderPreference` and `PushSubscription`.
  Streaks are computed, not stored — a stored streak is a cache that goes wrong quietly.
- **Calories**: `MET × weight_kg × hours` (DOMAIN §10), using `Sport.met_value`. A player
  who has not given their weight still gets a number, from the fallback, and the row is
  flagged `is_estimate` so the UI can say "estimated" instead of implying precision.
- **A week runs Saturday to Friday, in Dhaka** (D56). Bangladesh's weekend is Friday and
  Saturday, so an ISO week would cut a Friday-night match off from the Saturday-morning
  one that belongs with it. Every boundary is tested in Dhaka time.
- **The streak counts matches only.** A player could otherwise keep one alive by typing in
  a walk, and the streak is about turning up to play. It also survives the current week
  until that week is over, which is what makes it worth saving.
- **Bundles** are added whole in one tap. Partial stock adds what is there and names what
  is missing — refusing the lot because the bananas ran out is the worse answer. A bundle
  is always sourced from whoever owns it, so the Phase 08 "one order, one source" rule
  still holds.
- **Reminders** (Celery beat): match-day summary, hydration two hours out, a recovery tip
  after the whistle, and a Saturday-morning weekly recap. Every one asks `should_send`
  first — switched off, or inside quiet hours, means nothing is sent — and each is
  idempotent per match or per week, because beat runs them repeatedly.
- **The recovery job doubles as the activity safety net**: a match that finished with no
  scorecard still gets logged, so a player's week is right whether or not anybody filled
  the card in.
- **Web push** (D55) through `pywebpush`, opt-in per device, skipped entirely when there
  are no VAPID keys (development and CI). A subscription the push service reports as gone
  is deleted — that is the only way a browser tells us it has forgotten.
- **Live updates over SSE** (D54): Redis pub/sub fans a notification out to whichever
  worker is holding a player's stream. The client reads it with `fetch`-streaming so the
  token travels in a header rather than a query string, and a stream that will not open
  is not an error — the bell already polls.
- **Frontend**: a home dashboard (next match, the week as a ring, streak, suggested kit,
  open matches nearby), an activity page (twelve-week bars, history, goals, manual entry),
  bundle cards in the store, and reminder settings with push opt-in. A service worker
  handles push and nothing else — caching an authenticated app badly is worse than not
  caching it.
- **Tests**: 1240 backend (81 in `apps/fitness`), 17 Vitest, 97 Playwright.

**Verified in the browser** (Chrome DevTools, real Clerk session): the home dashboard
showed the next match, 60 minutes and ~515 kcal from a locked match, and a one-week
streak. Set a 180-minute weekly goal, added a 45-minute gym session, and the ring moved to
105/180 with the session in the history. Added a kit to the cart in one tap (2 protein
bars + water). Switched the hydration reminder off and confirmed it persisted. Opened the
SSE stream with a bearer token, sent a notification from a separate process, and watched
the frame arrive — `event: notification` with the rendered title and body. No console
errors.

**Two things the browser caught**

- The bundle "add to cart" passed the match's turf as a source hint, which can never work:
  a platform bundle's products are platform rows, and no turf stocks those. A bundle now
  comes from whoever owns it, and the parameter is gone.
- The reminder switches waited for the server before moving, which reads as a broken
  toggle. They are optimistic now, and revert if the save fails.

**Deviations / notes**

- `/api/v1/store/home` was returning an untyped body (`responses={200: None}`), so the
  generated client typed it `never`. It has a serializer now; an untyped endpoint is a
  hole in the generated client, not a shortcut.
- The SSE endpoint is excluded from the OpenAPI schema: it is `text/event-stream`, and
  describing it as an operation with a JSON body would be a lie.
- `fetchClientConfig` now also carries `week_starts_on` and the **public** VAPID key, so
  the browser can subscribe without a second round trip.

**Known gaps / follow-ups**

- SSE needs an ASGI server in production (`gunicorn -k uvicorn.workers.UvicornWorker`);
  `runserver` is threaded and handles it in development. The deployment change is noted in
  D54 and belongs to Phase 11.
- Live scoring over the same channel (Phase 05 step 5b) is still not built, and still
  needs your confirmation.
- VAPID keys are unset, so push is dark in development. Generating a pair and setting
  `VAPID_PUBLIC_KEY` / `VAPID_PRIVATE_KEY` turns it on with no code change.
- The weekly recap and match-day jobs are covered by tests and beat, not by a browser run
  — there is nothing to watch for a week.
- django-storages is still not wired up (carried from Phase 02).
- e2e still is not in CI; it needs `CLERK_SECRET_KEY` as a repository secret.

### Phase 10 — Online payments, advances, ledger and payouts (2026-11-04)

**Built**

- **A provider abstraction** (`apps/payments/providers/`): `PaymentProvider` with
  `start`, `validate` and `refund`, returning dataclasses (`StartedPayment`,
  `ValidationResult`, `RefundResult`) rather than raw gateway dicts — so a second
  gateway is a new class and a settings entry, and `services.py` never learns a
  provider's vocabulary. `CashProvider` is the existing counter flow behind the same
  interface; `SSLCommerzProvider` speaks v4 (`gwprocess/v4/api.php` to open a session,
  `validator/api/validationserverAPI.php` to validate, `merchantTransIDvalidationAPI.php`
  to refund).
- **Nothing is settled from the browser's return** (D57). `validate()` makes a
  server-to-server call and refuses on any of three checks: the status must be `VALID`
  or `VALIDATED`, the `tran_id` must be the one stored on the payment, and the amount
  must match to the paisa. The return page and the IPN both call the same
  `settle_payment`, which returns early when the payment is already `PAID` — so a
  duplicate IPN, a refreshed return page, and both at once all settle exactly once.
  The IPN answers **200 for a payment it has never heard of**: a gateway retries a
  non-2xx for hours, and there is nothing to retry towards.
- **Advances** (D60): `Turf.advance_percent` decides how much is due up front, a paid
  advance confirms the booking even for a player D3 would have held, and the balance is
  payable in cash at the counter or online. `mark_paid(..., record_payment=False)` stops
  the counter recording a second cash payment for money that came through the gateway.
- **Refunds follow a policy table**, not a judgement call (`refund_due`): the turf
  cancelled — everything back; the player cancelled inside the free window — everything
  back; the player cancelled late — the advance is forfeited and the rest comes back.
  A booking with no separate advance treats the advance share of its price as the
  deposit, which is what makes a full prepayment behave like everybody else's.
  `GET /api/v1/bookings/{id}/refund-policy` answers the same question before anybody
  commits to cancelling.
- **A ledger that cannot be written unbalanced** (D58): `post_entries()` raises before it
  writes unless the lines of one event sum to zero. Entries are signed and grouped by an
  `event_id`, so a ৳1000 booking at 10% is one event of three lines — player −1000, turf
  +900, platform +100. `unbalanced_events()` is there for an auditor, and a test asserts
  it is empty across the whole database.
- **`CommissionPlan`** per turf with a platform default created on first use, because a
  turf with no plan is on the default — a normal state, not a missing row to raise about.
- **Payouts** (D61): a statement per turf per period computed from the ledger, drafted by
  an admin, transferred by hand, then marked sent with its reference. The payout is itself
  a ledger event, which is what takes a paid-out turf's balance to zero instead of letting
  the same earnings be counted again next period.
- **Gateway replies are stripped before they are stored** (D59): `_safe()` drops
  `store_id`, `store_passwd`, `card_no`, `verify_sign` and `verify_key`. Card numbers and
  our own credentials never reach a database row, a log line or an error report. The
  player-facing serializer drops `raw_response` entirely.
- **Frontend**: a pay button on bookings and checkout (cash / pay the advance / pay in
  full), a redirect-and-return page that settles and then shows the result, payment
  history for players, an owner finance page (earnings by type, commissions, payouts and
  a CSV statement) and an admin finance dashboard with a payout board.
- **Tests**: 1310 backend (58 in `apps/payments`, covering success, failure, cancel,
  duplicate IPN, a tampered amount, a mismatched `tran_id`, the refund policy table and
  the ledger invariant), 17 Vitest, 105 Playwright.

**Verified in the browser** (Chrome DevTools, real Clerk session, against a local stub of
the gateway): paid a ৳350 advance on a ৳1000 booking, came back through the return URL and
watched the booking flip to **Confirmed** with the balance shown as payable at the turf.
The ledger read player −350, turf +315, platform +35 — three lines, summing to zero.
Confirmed `raw_response` held neither card data nor credentials. Drafted a payout for the
turf from its statement, marked it sent, and the turf's balance went to zero with
`unbalanced_events()` still empty. The duplicate-IPN, tampered-amount and mismatched-
`tran_id` cases are covered by `apps/payments/tests/test_callbacks.py` rather than by hand:
a forged callback is not something to click through.

**What the browser caught**

- The IPN crashed on a non-UUID reference — a gateway sending junk, or a test doing so,
  should get a 200 and be forgotten, not a 500 and a retry loop.
- Marking the balance paid at the counter recorded a *second* cash payment for a booking
  whose advance had already arrived through the gateway, so the ledger counted the money
  twice. `mark_paid(..., record_payment=False)` is the settlement path's answer.
- `cancel_order` told a delivered order it was "being prepared", because the status check
  ran after the message was chosen.
- The platform finance endpoint was untyped, so the generated client typed it `never` —
  the same hole Phase 09 found in `/store/home`. It has a `PlatformFinanceSerializer`
  now, and so does the turf statement.

**Deviations / notes**

- The ledger is double-entry *in the sense that counts* — every event's lines sum to zero
  — not a full chart of accounts. Accounts are `platform`, `delivery` and `turf:<id>`,
  which is what the payout statement and the platform dashboard need.
- `Booking` now exposes `player_profile_id` and `is_mine`; the payment screens need to
  know whose booking they are looking at, and a reader-relative flag is cheaper than a
  second request.
- `manage.py generate_vapid_keys` now mints a web-push key pair in the exact encoding the
  browser wants, and `.env.example` documents every new variable — the Phase 09 entry
  left "generate a pair" as an exercise, which is how a launch step gets skipped.
- The e2e slot helpers moved into `e2e/support/booking.ts`. Repeated runs book real slots
  that nothing releases, so every booking spec now hunts across turfs, days and grounds,
  waits for the grid before deciding a ground is full, and retries when another worker
  takes the slot first. Clerk's rate limit is also retried with backoff — a 429 after
  fifty sign-ins says "later", not "your app is broken".

**Known gaps / follow-ups**

- **Credentials needed from you**, before this can be pointed at the real gateway:
  a **SSLCommerz sandbox store ID and store password** (free, from their sandbox portal)
  to replace the stub; and for live, a **merchant account** plus a **registered public IP
  address** — SSLCommerz refuses refund API calls from unregistered IPs, so the server's
  egress IP has to be declared to them. Set `SSLCOMMERZ_STORE_ID`,
  `SSLCOMMERZ_STORE_PASSWORD` and `SSLCOMMERZ_SANDBOX`; with none set, the provider is
  unavailable and only cash is offered.
- bKash direct is not built. It goes behind `PaymentProvider` with no change above it.
- Payout transfers are manual by decision (D61), not by omission.
- SSE still needs an ASGI server in production (carried from Phase 09).
- Live scoring (Phase 05 step 5b) is still not built, and still needs your confirmation.
- django-storages is still not wired up (carried from Phase 02).
- e2e still is not in CI; it needs `CLERK_SECRET_KEY` as a repository secret.

### Phase 11 — step 1 of 9: Bangla and localisation (2026-11-04)

Phase 11 is nine steps and is being done one step per commit, as its brief allows. The
written audit it asks for is `docs/phases/11-audit.md`: seven blocking findings, eight
should-fix, and the order they are being worked in. This entry covers step 1.

**Built**

- **707 of 950 translation keys were still English placeholders.** All 950 are now Bangla,
  written by hand, namespace by namespace. The only two strings left identical are
  `৳{price}`-shaped format strings with no words in them — and both of those are gone
  too, replaced by a component (below).
- **Two stale Bangla values the usual check could not see**: `nav.myBookings` read "My
  bookings" while English had been rewritten to "Bookings", and `owner.empty` still
  promised "Turf registration arrives in Phase 02". Comparing the two strings finds
  neither, because they differ — looking for Bengali script finds both, and that is now
  a test.
- **Three i18n tests**, because 700 hand-written strings need a net under them:
  - every message takes the **same ICU arguments** in both languages, read from the
    parsed message rather than by regex (inside a `select`, the branch bodies are
    themselves brace-wrapped messages, so `{Hydration}` looks exactly like a placeholder
    to a regex and is nothing of the kind) — this also pins `select` option names and
    plural categories, which a translator can silently rename;
  - **no Bangla value is left in English**;
  - the existing key-parity and no-empty-string tests still run.
- **One place decides how money and dates look** (`src/i18n/formats.ts`): named date
  styles, `formatMoney`, `formatWhen`, `formatDay`, and the numeral system. Before this,
  38 places interpolated a Decimal straight out of the API next to a ৳ — so every price
  in the app read **৳1200.00**, trailing paisa that are always zero — and 22 places
  called `Intl.DateTimeFormat("en-GB", …)` with six near-identical option objects, so
  every date stayed English however the rest of the page read.
- **`<Money>` and `<When>`** (`src/components/ui/`), with no `"use client"` on purpose:
  `useLocale` works on both sides of the boundary, so a server page renders them without
  shipping any JavaScript. Paisa appear only when there are any (৳1,200, but ৳337.50),
  and a missing price is **—** rather than ৳0 — "no price set" and "free" are different
  facts, and a ground with no price rule cannot be booked at all.
- **Bangla reads in Western digits** (D62): `Intl` would give ০১২৩ for `bn`, and every
  money app these players already use writes Bangla prose with `0123`. English formats
  as **en-GB**, which is what each call site had spelled out — bare `en` means American
  to `Intl`, so centralising naively would have turned every 19:30 kick-off into
  07:30 PM. A test caught that before it shipped.
- **Hind Siliguri** via `next/font`, appended to the Latin stack rather than replacing
  it: font fallback is per glyph, so English keeps the platform face and only Bengali
  codepoints reach the Bengali font.
- **Catalogue labels are translated in the database** (D63): `*_bn` columns on `Sport`,
  `ProductCategory`, `Attribute`, `SportSkill`, `StatDefinition` and `SportFormat`, with
  50 Bangla terms seeded through the existing catalogue sync. Resolution is per request,
  from `Accept-Language` — which both API clients now send from the active locale —
  through `LocaleMiddleware` and one helper. Proper nouns are left alone.

**Verified in the browser** (Chrome DevTools, production build, `NEXT_LOCALE=bn`): the
whole header in Bangla, the public scorecard reading **ফুটবল · DHANMONDI ARENA** with the
stat column headed **গোল**, the date as **৫ নভে** — in Bangla with Western digits — and
Hind Siliguri resolved in the computed font stack. The turf's name is untouched, which is
the point of D63. No console errors.

**Deviations / notes**

- `player.heading` and `player.empty` were dead keys (nothing scoped a translator to that
  namespace) whose copy still said "Bookings arrive in Phase 03"; deleted. `admin.empty`
  promised "Review queues arrive in Phase 02" and now describes what is there.
- `turfs.taka` and `turfs.selectedSlot` are gone: they existed to interpolate a raw
  decimal next to a ৳, which is exactly what `<Money>` replaced.
- Product names are **not** translated, by decision rather than omission (D63): they are
  brand names — "Mum 500ml", "Spa Water" — and nobody writes those in Bangla either.
- The Open Graph image route still formats its date in English. It renders in Satori,
  outside the next-intl tree, and a link preview in a group chat is not a localised
  surface.

**Known gaps / follow-ups**

- **A native speaker still has to read the 707 strings.** They are idiomatic rather than
  literal, and some choices are worth arguing with — "ধারা" for a streak, "ভরসা" for
  reliability, "হিসাব" for finance. The ICU-argument test makes a correction safe to
  apply; nothing else here needs to change.
- Notification and email templates (`apps/notifications/templates.py`) are still English
  only. They are rendered server-side at creation (D31), so translating them needs the
  recipient's language stored on the account — which is step 1 work that properly belongs
  with step 5's `PlatformSetting`, and is listed there.
- Steps 2–9 of Phase 11 remain: PWA, performance, security, observability, admin tools,
  legal pages, deployment (needs a hosting decision from you) and the seven launch
  journeys.

### Phase 11 — step 2 of 9: the installable app (2026-11-04)

**Built**

- **A web app manifest** (`src/app/manifest.ts`): standalone display, portrait, the brand
  green as `theme_color`, and three shortcuts (find a match, my bookings, store) that
  land on the long-press menu of an installed icon. Without this the browser never offers
  to install, and in a market with no app-store listing an installed icon is how the app
  gets opened a second time.
- **Icons are drawn, not committed** (`src/app/icons/[size]/route.tsx`): one definition
  renders the 192, the 512 and the maskable variant through `ImageResponse`, so they
  cannot drift apart and there are no binaries in the repo nobody can diff. The maskable
  one is not simply a bigger icon — Android crops it to the launcher's shape, so the mark
  sits inside the middle 60% with the colour bled to the edges. Without a maskable icon
  most Android launchers letterbox the square inside a white circle.
- **The service worker caches exactly one thing**: the offline page. Everything else —
  every API call, every authenticated page — goes straight to the network, because a
  cache that serves one player's bookings to the next is worse than no cache at all
  (the Phase 09 note said as much; this keeps it). The fetch handler only runs for
  `mode: "navigate"` and only when the network has already failed.
- **The offline page is bilingual and has no translator.** It is cached once, at install
  time, so a localised version would be frozen in whichever language was active that day
  — and the one moment somebody reads it is the moment nothing can be asked of the server.
  Two short blocks is cheaper than being wrong.
- **Registration moved out of the push opt-in.** Phase 09 registered the worker only when
  a player turned notifications on, which left the offline page cached for nobody else.
  It now registers on every visit; push stays opt-in because it needs a *subscription*,
  which registration does not create.
- **An install prompt that appears once** (`install-prompt.tsx`): it listens for
  `beforeinstallprompt`, so there is nothing to feature-detect — no event, no banner, and
  Safari correctly never shows it. Dismissal sticks in `localStorage`, because a prompt
  that returns every visit is an advert.
- **Four Playwright tests**, unauthenticated: the manifest parses and names all three
  icons, every icon the manifest names is a real PNG, the offline page stands alone in
  both languages, and the registered worker has actually cached it. A 404 icon makes the
  app silently non-installable and nothing else in the suite would notice.

**Verified in the browser** (Chrome DevTools, production build): the worker installed and
activated at scope `/`, `turfapp-offline-v2` held the offline page, and the manifest
served all three icons. Then **the server was stopped** and `/turfs` navigated to — the
cached offline page rendered in place of Chrome's error page, which is the only test of
an offline fallback that means anything. Restarting and updating the worker deleted the
v1 cache and replaced it with v2, so bumping the name is how the page is changed.

**Deviations / notes**

- `maximum-scale` is deliberately not set: blocking pinch-zoom on a phone-first app
  removes an accessibility feature to tidy a layout.
- The cache name carries a version (`turfapp-offline-v2`) and `activate` deletes every
  other cache. That is the whole invalidation story, and it is enough for one static page.

**Known gaps / follow-ups**

- Low-end Android over throttled 3G has not been measured yet — that is step 3
  (performance), which also owns the image and query work.

### Phase 11 — step 3 of 9: performance (2026-11-04)

**What the query budgets found**

The point of writing them was that an N+1 never fails a test, raises an error or shows
up in review — it shows up as a page that is fine with three rows and unusable with
thirty. Two of the four endpoints measured had one:

- **The match board cost one extra query per card.** `average_rating_for` asked "is the
  annotation None?" to decide whether to fall back to a query — but a board row whose
  roster is entirely unrated *is* annotated NULL, and that is the answer (D38 keeps such
  a match on the board), not a missing annotation. So the busiest authenticated page in
  the app went back to the database once per match, and did so hardest for exactly the
  matches full of new players. The test is now `hasattr`. 3 matches cost 5 queries; 15
  matches now cost the same 5, where they used to cost 17.
- **The match page cost one extra query per player on the roster.** Each roster row
  shows that player's rating *in this sport*, read off `profile.sport_ratings`, which
  the prefetch did not cover. Adding it to the `Prefetch` queryset flattened 20 queries
  back to 12 for an eight-player roster.

`apps/core/tests/test_query_budgets.py` keeps both fixed. Each test asserts a ceiling and
then — the assertion with teeth — that the **same request with many more rows costs the
same number of queries**. The ceilings are deliberately not exact: a test that fails when
somebody adds a legitimate `select_related` teaches people to raise the number without
reading it.

**A caching policy, written down and tested**

`apps/core/cache.py`, with two rules that are the whole of it:

1. **Nothing per-player is cached.** Every page behind a session is built from that
   player's own rows, and a key loose enough to be useful would be loose enough to show
   one player another's bookings. The service worker makes the same call (step 2).
2. **What is cached is public and already stale.** The leaderboard is recomputed
   overnight and read all day; the turf page changes when an admin approves a venue.

So two things are cached: the **leaderboards** (an hour, invalidated by the nightly
rebuild task itself) and the **public turf page**, per slug *and per language* — it
carries sport names, which are now translated (D63), and one entry for both languages
would serve whichever reader arrived first. The turf **list** is deliberately not cached:
its `near=` variant is keyed by the caller's coordinates, so the key space is unbounded
and the hit rate would be roughly zero.

Invalidation is by **version key** — bump one integer and every key derived from it
becomes unreachable at once — driven by a signal on every model that feeds the turf page
(`apps/turfs/signals.py`). Hooking the models rather than the dozen endpoints that edit
one is the only version that still works after somebody adds a thirteenth. A test asserts
an owner who renames their turf sees the new name on the next request, and another pins
the invariant that makes caching the page safe at all: two different players get byte-for-
byte the same payload.

**Measured, not assumed** (Chrome DevTools, Slow 3G + 4× CPU throttling, Pixel-class
viewport, cold cache — the brief's "low-end Android over slow 3G"): **LCP 3.7s, CLS
0.04**. The only render-blocking resource is one stylesheet, and it is already 13.5 kB
gzipped — there is nothing left to squeeze in the app. The remaining 1.2s of that
download is bandwidth and HTTP/1.1 on a local server; a CDN with HTTP/2 and Brotli is
what fixes it, and that is step 8. Off-screen images (turf photos, roster and search
avatars) are now `loading="lazy"` and `decoding="async"`, which is the one thing on the
page that was still free to improve.

**Deviations / notes**

- **Cache Components stays off**, revisited as D14's note asked. The reason has not
  changed and is not a matter of effort: almost every page renders one player's own data,
  so there is nothing a shared render cache can hold. What is shared and expensive is
  cached server-side instead, where it can be invalidated when the data changes.
- **Indexes were audited, not added.** The board's `(visibility, status)`, the turf
  list's `(status, area)`, rating history's `(profile, sport, -played_at)`, ground stats
  and the bookings GiST exclusion constraint all already cover the hot paths. Adding
  indexes nothing queries is a cost, not a safeguard.
- **Resized uploads are not built**, because there is nowhere to put them: django-storages
  is still not wired up (carried since Phase 02), so there is no upload pipeline to resize
  in. It belongs with step 8.

**Known gaps / follow-ups**

- Only four endpoints have budgets. The scorecard, store checkout and owner finance pages
  build nested payloads too and should get one each.
- No load test yet — step 9 owns that, against staging.

### Phase 11 — step 4 of 9: security (2026-11-04)

**The permission matrix, and what it was for**

167 routes were added by hand across eleven phases, and the failure mode is silent: one
missing `IsAuthenticated` is a data leak no feature test notices, because every feature
test is already signed in as somebody. `apps/core/tests/test_permission_matrix.py` walks
the **URL conf itself** rather than a list somebody maintains — a route added tomorrow is
covered tomorrow — and asserts three things:

- every route refuses an anonymous request, unless it is named in `PUBLIC_ROUTES` **with
  a reason**, which makes opening one an argument in a diff rather than a discovery in a
  log;
- every open route is one of those eleven, and no more;
- every admin route refuses an ordinary signed-in player.

A URL built wrongly 404s, and 404 is not in the accepted set — so a broken test URL fails
loudly instead of passing for the wrong reason, which is the failure mode that would make
the whole file worthless.

**What it found**

- **The complete API schema and two interactive documentation UIs were open to the
  world.** 167 endpoints, their payloads and their parameters — the first thing anybody
  probing the API would want. They are now gated by `API_DOCS_PUBLIC`: open locally so
  `npm run gen:api` needs no credentials, platform admins only once deployed. The test
  settings use the *production* posture, so the matrix covers those routes for real.
  (The gate had to go in `SPECTACULAR_SETTINGS["SERVE_PERMISSIONS"]` — drf-spectacular's
  views read that and ignore `permission_classes` passed to `as_view()`.)
- **A player's email address was being used as their display name in eleven places.**
  Every roster row, board card, timeline entry and audit line falls back to *something*
  when a player has not set a name, and that fallback was `user.email` — so anybody who
  signed up and did not finish onboarding had their email shown to everyone who could see
  the match. There is now one `player_label()`: the profile name, else the account name,
  else the neutral word "Player". Two unnamed players look alike, which is the correct
  trade — they are strangers about to turn up to the same pitch, not people who need to
  identify each other. The grep that found it is kept as a test.
- **Image uploads had no size and no pixel limit.** `ImageField` refuses anything Pillow
  cannot open, which stops the obvious "rename a script to .png", but it bounds nothing:
  a turf photo could be a 500 MB file, or a 20,000 × 20,000 PNG that unpacks to over a
  gigabyte the moment anything reads it. Now 5 MB and 6000 px a side, with Django's own
  `DATA_UPLOAD_MAX_MEMORY_SIZE` as the cruder guard that runs first, and messages a
  person can act on ("that image is 12.4 MB; the limit is 5").

**Rate limiting, and the mistake worth recording** (D65)

Nothing was metered at all before this: one script could fill a player's inbox with join
requests, flood the admin conduct queue, or walk the whole player directory.

The first attempt set the anonymous limit to 60/min and **took the entire end-to-end
suite down**. The reason is worth keeping: DRF's `AnonRateThrottle` keys on IP, and every
server-rendered page reaches Django from the *frontend server's* single address — so a
thousand readers look like one caller, and a tight anonymous limit throttles the site
long before it inconveniences a scraper. It is a crude flood guard and nothing more.

So: `/api/v1/config` and the health probe are unthrottled outright (they are constants,
and a load balancer polling a health check must never be told to slow down), the
anonymous ceiling is 1200/min, and the limits that do real work are **scoped per user**
on the actions that reach another person — invites and join requests 20/hour, conduct
reports 10/hour, player search 120/hour. Searchable is not the same as scrapeable, and
the difference is a rate. A test drives one past its limit and asserts the 429; another
asserts that reading the board forty times in a row is still fine, because the day these
limits start interrupting somebody filtering interactively is the day they are wrong.

**A content policy with a real nonce**

There was none. It could not go in `next.config.ts`, because the App Router emits inline
`<script>` tags carrying the flight payload on every page and a static policy can only
allow those with `'unsafe-inline'` — which is most of what a script policy is for. So
`src/proxy.ts` mints a nonce per response, sets the policy on both the request (where
Next reads it back to stamp its own scripts) and the response, and `ClerkProvider` is
handed the same nonce — Clerk renders its own `<script src>`, and under `'strict-dynamic'`
host allowlisting is disabled, so without the nonce sign-in simply stops working. Also
set: `Referrer-Policy`, `Permissions-Policy` (geolocation and notifications only, camera,
microphone and payment denied), `nosniff` and `X-Frame-Options: DENY`.

**The Django admin now wants a second factor** (D64)

Clerk guards player and owner accounts and brings its own, but `/admin/` is a separate
door with a separate password, and behind it is every booking, every payment and every
player's details. `django-otp` with TOTP, `OTPAdminSite`, off in development and on in
production. The new dependency is justified in D64 as CLAUDE.md asks.

**Dependency audits in CI**: `npm audit --audit-level=high` and `pip-audit` against the
exported production requirements. Both pass today. `--audit-level=high` is deliberate —
all 22 current npm advisories are moderate, every one of them in `minimatch` or eslint
tooling that never reaches the bundle, and a job that cries wolf gets disabled.

**Verified in the browser** (Chrome DevTools, production build): the policy header is
served with a fresh nonce per response, Next's inline scripts carry it, Clerk loads, the
page hydrates and the console is clean. Before the nonce was passed to `ClerkProvider`
the console showed exactly the failure described above, which is how that line got
written.

**Tests**: 1517 backend (the permission matrix is parametrised over every route, so it
grows with the URL conf by design), 26 Vitest, 113 Playwright — all green under the new
content policy, which is the run that matters: a policy that breaks sign-in would pass
every unit test ever written.

**Known gaps / follow-ups**

- CORS still allows the development origins; the production list is part of step 8.
- The admin TOTP device has to be registered by hand after the first deploy — there is
  no bootstrap flow, and for one or two administrators there should not be.
- Notification and email templates remain English-only (carried from step 1).

### Phase 11 — step 5 of 9: observability and operations (2026-11-04)

**`PlatformSetting`, finally** (D66)

CLAUDE.md has said since Phase 00 that configurable rules live in one place and that
`apps/core/utils.setting()` would be the only thing that ever learned about a database.
That is now true: a row overrides the code's default, deleting it restores the default,
and nothing else changed anywhere.

The direction matters. The app is always runnable with an empty settings table, and
undoing a bad edit is deleting a row rather than remembering what the number used to be.
Values are text, read back as the type of the code's default — a column per type would
make the admin form worse for the people who use it — and **an unparseable value falls
back rather than raising**, so a typo degrades to yesterday's behaviour instead of
taking the site down. There is a test for exactly that. Reads are cached for a minute:
long enough not to be a query on every booking, short enough that "without a deploy"
stays true, and the admin clears the key on save so somebody who just pressed save sees
their change.

The admin shows **what the code's default is** next to each row, because an admin about
to change a number should be able to see what they are overriding.

**Error reporting** (D67)

Sentry in all three processes — web, worker and beat — started from one place and
**initialised only when a DSN is configured**, the same shape web push uses (D55). No
account needed for development or CI, and no `if (sentry)` anywhere in the app.

What is deliberately not sent:

- **Request bodies.** A booking payload carries a phone number; a payment callback
  carries a transaction reference. An error report is not a place to keep either.
- **Anything credential-shaped**, through a scrubber on *both* sides that redacts the
  names this app actually uses. `store_passwd` is SSLCommerz's spelling, not a convention
  a generic denylist would guess — D59 keeps it out of stored responses, and this keeps
  it from reaching a third party as well.
- **Session replay.** It would record players' own screens, including their phone numbers
  and delivery addresses, to somebody else's server.

Celery is integrated too, because the timers that confirm bookings and close votes are
exactly where a failure is silent: the site looks fine and nothing has auto-confirmed
for six hours.

**Structured logging**: JSON where something is going to index it, the readable one-line
format where a person is reading the terminal. Every log call in the codebase already
passed its facts through `extra=`, so **no call site changed** — only the formatter,
which now keeps those fields at the top level of each line instead of discarding them.

**The health endpoint now reports its dependencies**, not just itself: the database,
PostGIS, the cache, and how many Celery workers answered a ping. Redis is not optional
here — it is the cache, the broker and the Phase 09 pub/sub channel — so a 200 while it
is down would tell a load balancer to keep sending traffic; it returns 503 instead.
Worker count is `null` when the broker could not be asked, which is a different fact
from "none are running" and reads that way on a status page.

**Backups that have been restored** (D68)

`manage.py backup_database` dumps **and then restores the dump into a scratch database
and counts the tables**, failing if what came back is not usable. The failure mode of a
nightly dump is finding out on the day it matters that it has been zero bytes for three
months, and the only thing that catches that is restoring it. Old dumps are pruned to the
last fourteen.

**Verified by running it**: dumped the development database (2.1 MB), restored it into a
scratch database, counted 90 tables, dropped the scratch. It also failed correctly on the
first attempt — `pg_dump` 16 against a server running 17 — which is a real deployment
hazard the docstring now names.

**Deviations / notes**

- **No Flower, no Prometheus, no log pipeline** (D67). A pilot in two Dhaka
  neighbourhoods needs to know when a booking failed for somebody, not a metrics stack.
  Sentry's Celery integration reports a task that dies — the thing Flower is mostly
  watched for — and the health endpoint answers "are there any workers at all".
- `@sentry/nextjs` v11 removed `sendDefaultPii`; personal data is no longer attached by
  default, which is the right default but is not a guarantee. The scrubber is the
  guarantee.
- The backup command is a management command, not a Celery task: a worker that is down
  cannot back up the database, which is precisely when you want the backup. Where it
  runs from is step 8's decision.

**Known gaps / follow-ups**

- Nothing *calls* `backup_database` yet — scheduling it, and putting the dumps somewhere
  that is not the application server, belongs to step 8.
- Uptime checks need an external prober pointed at `/api/v1/health`; also step 8.
- No settings rows are seeded. That is correct — every rule still has its default in
  code, and a row should exist only once somebody has deliberately changed something.

### Phase 11 — step 6 of 9: admin and support tools (2026-11-04)

**Built**

- **A dashboard that says whether the pilot is working** (`/admin/dashboard`): bookings
  and how many were confirmed, the no-show rate, active and new players, live and pending
  turfs, platform earnings and commission, matches, orders, a bookings-a-day chart and the
  busiest turfs — over 7, 30 or 90 days. Every number was already derivable from rows the
  app writes; what was missing was anywhere to read them together. An owner had a finance
  page and an admin had four separate queues, but nobody could answer "how many bookings
  yesterday, and how many of them did somebody turn up to".
- **The no-show rate is counted against bookings that reached their slot**, not against
  every booking ever made. A cancelled booking is not a no-show, and including them would
  have flattered the number exactly as the business grew — which is the one direction a
  metric must not drift.
- **"Active" means a player who did something**, not one who exists. A sign-up that never
  books is not a user of this app, and counting them makes the number useless for the
  decision it is for.
- **Days with no bookings are rendered**, not skipped. A chart that silently drops them
  draws a healthy-looking line straight through an outage. The chart is divs, not a
  charting library: one series over at most ninety points, and shipping a canvas renderer
  to draw ninety rectangles is a poor trade on the connections this app runs on.
- **GMV is read off the ledger**, not re-derived from bookings and orders, so the
  dashboard cannot disagree with the finance page about how much money moved.
- **A support lookup** (`/admin/support`): find an account by name, email or phone. The
  Phase 06 player search cannot do this on purpose — it is limited to discoverable
  players and never exposes contact details — so this is the deliberate exception, and it
  is narrow: platform admins only, three characters minimum (two would return most of the
  directory), what support needs to tell two Rafis apart and nothing more, and **no
  impersonation anywhere** — an admin can read an account, never act as one.
- Computed on demand rather than rolled up nightly: these are read a few times a day by a
  handful of people, and a rollup table is a second source of truth that goes quietly
  wrong. The leaderboards earn that treatment because everybody reads them all day; this
  does not.

**What building it found**

- **The email-as-display-name leak was still live, one layer down.** Step 4 replaced the
  fallback in eleven serializers; `PlayerProfile.name` — which sits *underneath* all of
  them and is what `player_label()` prefers — still ended in `self.user.email`. So a
  player who had started onboarding but set no name was still having their email shown to
  everybody who could see the match. Fixed, and the test now covers both paths: the step 4
  test only checked a player with no profile at all, which is why it passed.
- **The "Debug" link was in the header for everyone**, pointing at `/me`, which dumps the
  raw backend session. Development only now.

**Verified in the browser** (Chrome DevTools, production build, signed in as a real
platform admin): the dashboard rendered 439 bookings over 30 days with 4 confirmed, a 0%
no-show rate, 432 active players, ৳350 platform earnings of which ৳35 commission, the
per-day chart with its peak marked, and the six seeded turfs ranked by bookings —
Dhanmondi 160, Banani 92, Mirpur 87. The support lookup for "rafi" returned the two
accounts that share that name, distinguished by their email addresses, which is exactly
the problem it exists to solve. No console errors.

The chart gained a baseline afterwards: without one, a day with no bookings rendered as
nothing rather than as a zero, which is the chart's whole job.

**Deviations / notes**

- The existing queues (turfs, sports, conduct, orders, finance) were **not** merged into
  one screen. They are each a working queue with their own actions, and collapsing five
  of them into tabs would make every one of them worse; the admin index now links to all
  of them plus the two new pages.
- CSV export already exists where it is useful — the turf statement (Phase 10). The
  dashboard's numbers are a screen to read, not a file to reconcile.
- The Playwright suite asserts the **gate**, not the pages: it cannot grant itself
  platform-admin, which is the point of the role. The pages themselves were verified by
  signing in as a promoted throwaway account, which is how the screenshots above exist.

**Known gaps / follow-ups**

- No per-turf drill-down from the dashboard yet; the busiest-turf list links to the public
  page, not to that turf's own numbers.
- The dashboard has no query budget (step 3's tests cover four endpoints); it is
  admin-only and read a few times a day, so it is low on the list.

### Phase 11 — step 7 of 9: policies and content (2026-11-04)

**Built**

Four policy pages at `/legal/…`, public and linked from a new footer on every page:

- **Cancellation and refund policy.** Every rule in it is the one the code actually
  applies — `refund_due()` is the implementation of this document, and if the two ever
  disagree the code is the bug. This is also the URL SSLCommerz asks for during merchant
  onboarding, which is why it has to resolve without an account.
- **Privacy policy**, written from what the code stores and sends rather than from a
  template. It can say "your email address is never used as your name" and "request
  bodies are never sent to our error reporter" because steps 4 and 5 made both true.
- **Terms of use**, including the thing that most needed saying plainly: we are the
  platform, not the turf, and playing sport is at your own risk.
- **Turf owner agreement**: commission, payouts, and that a turf cancelling on a player
  refunds them in full out of that turf's own earnings.

**Each page is authoritative in English with a Bangla summary** (D69), and says so in
Bangla. Translating binding terms produces two documents that can disagree, and without
a Bangladeshi lawyer reading both versions there is no way to know when they do — worse
than one document plus an honest summary telling a reader what it says.

**No cookie consent banner** (D70), and that is a decision rather than an omission: the
only cookies set are the sign-in session and the language choice, both strictly necessary.
There are no advertising or analytics cookies and no cross-site tracking, so a banner
would ask permission for something that is not happening and train people to dismiss a
dialogue without reading it. The privacy policy says what is set and why instead.

The prose lives in `src/content/legal/`, not in `messages/*.json` — those files are the
UI string catalogue where the key-parity and ICU-argument tests earn their keep, and
three thousand words of prose would drown both.

**Verified in the browser** (Chrome DevTools, production build, Bangla locale): the
refund policy renders with its Bangla summary panel above the English text, the Bengali
set in Hind Siliguri, and the "if these disagree, the English governs" line in Bangla
underneath. Signed out, all four resolve; an unknown slug is a 404 rather than a blank
page. Six Playwright tests cover exactly that, because "a player can read it before
deciding to pay" is the property that matters, not the prose.

**Deviations / notes**

- "Last updated" and the footer are UI chrome and follow the reader's language; the
  document body does not, by design.

**Known gaps / follow-ups**

- **These drafts have not been reviewed by a lawyer, and must be before launch.** They
  are written to be accurate about what the software does, which is the part I can be
  sure of; whether they are sufficient under Bangladeshi consumer and data protection law
  is not something to assume. This is a launch blocker, listed here so it is not quietly
  skipped.
- The company's legal name, address and a support contact are not in them yet — they need
  to be, and they are facts I do not have.

### Phase 11 — step 8 of 9: deployment (2026-11-04)

**You chose DigitalOcean Bangalore and Vercel** (D71), which is what D11 left open since
Phase 00. Bangalore is the nearest region to Dhaka among the large providers — roughly
40–60ms — and managed Postgres and Redis rather than containers, because the backup,
failover and upgrade stories are better handled by somebody whose job they are.

**Built**

- **`backend/Dockerfile`** — one image, three processes. The API, the worker and beat run
  the same code and the same dependencies and differ only in their command; three images
  would be three things to keep in step, and the day they drift is the day beat runs last
  week's business rules. GeoDjango loads GEOS and GDAL through `ctypes`, so those are
  runtime libraries in the final image rather than build-time ones (D16 again, in a new
  place). Runs as a non-root user, collects static at build time so a restart cannot race
  `collectstatic`, and serves through **uvicorn workers** because the Phase 09
  notification stream is a long-lived response and a sync worker holding one is a worker
  serving nobody (D54).
- **`frontend/Dockerfile`** — not used on Vercel, and kept working anyway. `output:
  "standalone"` is scoped off under `process.env.VERCEL`, so the escape hatch is a real
  one rather than dead weight. A platform choice should not be welded into the code.
- **`.do/app.yaml`** — the App Platform spec: three services, managed Postgres 17 and
  Redis, and migrations as a **`PRE_DEPLOY` job** so a deploy cannot start serving
  requests against a schema it has not migrated. `beat` is pinned to one instance, with
  a comment saying it is the one number in the file that must not be raised: two beats
  mean every timer fires twice, and the jobs are idempotent per match and per week, not
  per run.
- **`docker-compose.prod.yml`** — the same topology runnable on one box, for anyone who
  wants it and as documentation of how the pieces fit.
- **Media on Spaces** (D71), closing a gap open since Phase 02. Through **S3-compatible**
  settings, not Spaces-specific ones, so moving to R2 or S3 is an environment change
  rather than a code change. A container filesystem is not a place to keep anything that
  has to survive a deploy, and until now that is exactly where turf photos went.
- **`.github/workflows/deploy.yml`** — waits for the checks on that commit, deploys,
  and **fails if the API does not come back healthy**. One deploy at a time: two
  overlapping ones race on the migration job, and the loser starts serving against a
  schema the winner has already moved.
- **`docs/DEPLOYMENT.md`** — the runbook, including the things that are easy to forget
  and expensive to discover: `CREATE EXTENSION btree_gist` (without it the migration that
  prevents double-booking fails), `CLERK_AUTHORIZED_PARTIES` matching the frontend origin
  exactly (the single most likely reason a working staging deploy stops authenticating),
  and **registering the server's egress IP with SSLCommerz** — they refuse refund calls
  from an unregistered address, so refunds fail in production while payments work, which
  only shows up the first time somebody cancels.

**What building the images found**

**A real bug, not a packaging one.** `process.env.NEXT_PUBLIC_SITE_URL ?? "…"` does not
do what it looks like it does: `??` catches `null` and `undefined`, and an environment
variable set to the **empty string** is neither. Docker turns an unset `ARG` into an
empty `ENV`, so `new URL("")` killed `next build` with `ERR_INVALID_URL`. Every container
platform behaves that way, so this would have failed identically on the first real
deploy. There is now one `env()` helper used at all seven sites, with a test.

**Verified by building and running both images:**

- Backend (948 MB): Django 6.1.2, GEOS constructing a Dhaka point, production settings
  confirmed live — `DEBUG` off, API docs closed, admin OTP on, JSON logs — and gunicorn,
  uvicorn and Celery all present.
- Frontend (422 MB): serves the home page, the policy pages and the manifest, with the
  content policy header intact. Its first run returned 500s, correctly: no
  `CLERK_SECRET_KEY` and no reachable API. With both supplied it serves 200s.

**Deviations / notes**

- **No BuildKit cache mounts.** They are faster and they make the file unbuildable on a
  Docker install without buildx — and an image nobody can build locally is one nobody
  checks before pushing. Layer ordering does most of the same work.
- The backend image is 948 MB, most of it GDAL and GEOS. That is the cost of PostGIS in
  the application layer and not worth contorting the build to avoid.

**Known gaps / follow-ups**

- **Nothing has been deployed yet.** The spec, the workflow and the runbook are written
  and the images build and run; the accounts, domains and credentials are yours to
  create, and step 9 runs the launch journeys against the staging environment that
  follows.
- The backup command needs scheduling once the app exists, and its dumps need to go
  somewhere that is not the application server.
- An external uptime prober should be pointed at `/api/v1/health`.

### Phase 11 — step 9 of 9: the launch journeys (2026-11-04)

The seven journeys from the phase brief, as `frontend/e2e/journeys.spec.ts`.

**These are not more feature tests.** Every step in them is already covered by a spec
that does one thing well; what they add is the **seams** — a booking becoming a match
becoming a scorecard becoming a rating, each handing to the next. That is where
integration bugs live, and no single-feature test can see them.

**What made them possible**

`seed_demo` creates `rafi+clerk_test@turfapp.dev` as a platform admin, the owner of
three turfs *and* a rider — in Clerk as well as in Django. Several journeys cross a role
boundary (an owner lists a turf and an admin reviews it; a player orders and a cashier
sells), and a suite that can only ever be one anonymous new player stops short of all of
them. One account rather than four, because roles here are permissions on an account,
not separate kinds of user (DOMAIN §1). Nothing is faked: it signs in through the same
ticket flow as every other test.

The other half is `openAsNewPlayer`, which opens a **second** browser context as a
second real player. A scorecard cannot lock without the opposing captain, and a rating
cannot move without a locked card — so journey 2 with one player would have stopped
three steps short of the thing it exists to prove.

**The seven**

1. **An owner lists a turf** and it starts as a draft invisible to players; the admin
   queue is reachable by somebody who holds that role.
2. **The spine**: onboard → book → somebody else finds the match and asks to join → the
   organiser approves → teams, with a captain on each side → the score → **the other
   side's captain confirms it, which is what locks it** (D41) → the locked card has a
   public page → the profile carries the sport. Two players, two contexts, end to end.
3. **A closed squad** and the D1 invite chain — the one flow where a player joins a match
   nobody advertised, needing three people's consent in order.
4. **An order for a match**: the store knows there is a match to deliver to, and offers
   delivery to the turf because the cutoff has not passed.
5. **Two shelves that must not move each other**: a player's home delivery comes out of
   the platform warehouse and leaves the turf's bananas alone; a cashier's counter sale
   moves the turf's shelf by exactly one and leaves the warehouse alone (D48).
6. **The money rules are visible before anybody commits to them**: paying online is
   offered *and so is cash*, the cancellation window is on the booking rather than buried
   in a policy page, and the refund quote comes from the server's own policy table —
   which is the number the refund will actually use, not a second implementation in the
   UI.
7. **The whole thing in Bangla at 390px**, including that the page does not scroll
   sideways.

**What writing them changed**

- **The booking helper no longer depends on English.** It reached for `getByLabel("Date")`
  and a button labelled "Book for ৳…", so journey 7 failed at the first step — which is
  exactly the bug a Bangla journey is for. It now uses `#date` and a `data-testid`,
  matching `#ground`, which was already doing the right thing.
- **Onboarding in the journeys is language-aware.** A helper that only worked in English
  would have quietly reduced journey 7 to a smoke test of the language switcher.
- `test.slow()` was replaced with an explicit timeout: its 3× multiplier turned a hung
  sign-in into a seven-minute wait and made the file miserable to work on.

**Deviations / notes**

- **These run against the local stack, not staging**, because there is no staging — you
  asked not to deploy, and step 8 created configuration rather than infrastructure. They
  are written to be environment-agnostic (`PLAYWRIGHT_BASE_URL`), so pointing them at a
  staging URL is a variable, not a rewrite.
- **Journey 6 does not complete a card payment.** The gateway leg needs SSLCommerz
  credentials, and the stub I used in Phase 10 was deliberately temporary. What it
  asserts instead is the part the app owns: both payment options offered, the window
  stated, and the refund quote coming from `refund_due` rather than a UI reimplementation.
  The gateway path itself is covered by `apps/payments/tests/test_callbacks.py`, including
  a forged callback and a tampered amount.
- Journey 1 stops at the review queue rather than approving: approving a turf needs the
  same account to be both owner and admin, and asserting that it can is a weaker test
  than asserting the draft is invisible until somebody with that role acts.

### Phase 11 — where the project stands (2026-11-04)

All nine steps are done. What is **not** done is a deployment: you asked for the build
to be completed rather than shipped, so step 8 produced the images, the platform spec,
the CI workflow and the runbook — and touched no account and no infrastructure.

**Before this can go live**, in the order it matters:

1. **A lawyer has to read the four policy pages.** They are accurate about what the
   software does, which is the part I can be sure of; whether they are sufficient under
   Bangladeshi consumer and data protection law is not something to assume.
2. **A Bangla speaker has to read the 707 translated strings.** They are idiomatic rather
   than literal, and some choices are worth arguing with — "ধারা" for a streak, "ভরসা" for
   reliability, "হিসাব" for finance. The ICU-argument test makes corrections safe to apply.
3. **Accounts and credentials**: DigitalOcean, Vercel, a Clerk *production* instance, an
   SSLCommerz merchant account, a domain. `docs/DEPLOYMENT.md` is the runbook.
4. **Then staging**, and the launch journeys pointed at it via `PLAYWRIGHT_BASE_URL`.

**Carried forward, still open**

- Live scoring over the Phase 09 channel (Phase 05 step 5b) — still not built, still
  needs your confirmation that it is wanted.
- The e2e suite is not in CI; it needs `CLERK_SECRET_KEY` as a repository secret. It runs
  locally against the production build on port 3000.
- Notification and email templates are English only. Translating them needs the
  recipient's language stored on the account, which is a small piece of work nobody has
  asked for yet.
- Only four endpoints have query budgets; the scorecard, checkout and owner finance pages
  deserve one each.
- No load test has been run.

**The numbers**: 1517 backend tests, 27 Vitest, 143 Playwright (including the eight
launch journeys), 71 decisions recorded, 11 phases.
