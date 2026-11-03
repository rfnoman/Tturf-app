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
