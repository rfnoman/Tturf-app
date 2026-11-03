# TurfApp — Project Brief for Claude Code

A platform for sports turfs in Bangladesh: turf owners list grounds and sell inventory,
players book grounds (solo or as a squad), fill matches with other players, record
scorecards, and build a FIFA-style profile. A platform store delivers fitness-focused
products to the turf or to the player's home.

**Read before any work:**
- `docs/DOMAIN.md` — business rules (the source of truth for behaviour)
- `docs/DECISIONS.md` — decisions taken on open questions (check before assuming)
- `docs/PLAN.md` — phase index; the current phase file lives in `docs/phases/`
- `docs/PROGRESS.md` — what is already built; update it at the end of every phase

## Stack
| Layer | Choice |
|---|---|
| Frontend | Next.js (App Router) + TypeScript, Tailwind CSS, shadcn/ui, TanStack Query, next-intl (en + bn) |
| Auth | Clerk (`@clerk/nextjs` on frontend; Django verifies Clerk session JWTs via JWKS) |
| Backend | Django + Django REST Framework, drf-spectacular (OpenAPI) |
| DB | PostgreSQL + PostGIS (`django.contrib.gis`) |
| Jobs | Celery + Redis (timers: hold expiry, auto-confirm, vote close, reminders) |
| Tests | pytest-django + factory_boy (backend), Vitest (frontend units), Playwright (e2e) |
| Local dev | docker compose (postgres/postgis, redis); backend and frontend run on host |

## Repository layout
```
turf-app/
  backend/            Django project
    config/           settings (base/dev/test/prod), urls, celery
    apps/
      core/           base models (TimeStamped, UUID pk), utils, permissions
      accounts/       User (clerk_id), roles, Clerk auth + webhook
      players/        PlayerProfile, per-sport ratings, onboarding (DECISIONS D19)
      sports/         Sport catalogue, attributes, skills, stat definitions
      turfs/          Turf, Ground, pricing, hours, staff membership, availability
      bookings/       Booking (+exclusion constraint), state machine, Celery jobs
      matches/        Match, Squad, JoinRequest, MatchInvite, match board
      scoring/        Teams, scorecard, player stats, MOTM, peer ratings
      ratings/        Rating engine, track record, leaderboards, conduct
      inventory/      Product, StockLocation, StockMovement, rentals, POS
      store/          Cart, Order, fulfilment, delivery zones and charges
      fitness/        Activity log, streaks, bundles, reminders
      payments/       Payment, providers (cash now; SSLCommerz/bKash later), ledger
      notifications/  In-app notifications, email, push
  frontend/           Next.js app
    src/app/          routes: (player), (owner), (admin)
    src/lib/api/      generated OpenAPI types + typed client
  docs/
  docker-compose.yml
```

## Conventions (follow strictly)
- **Business logic lives in `services.py`** per app (plain functions taking explicit args).
  Views/serializers stay thin. Read-heavy queries go in `selectors.py`.
- **State machines are explicit**: each stateful model has a `Status` TextChoices and a
  single service function per transition that validates the from-state, writes the new
  state, and records an event row (e.g. `BookingEvent`). Never set `status` directly elsewhere.
- **Money**: `DecimalField(max_digits=12, decimal_places=2)`, currency BDT. Never floats.
- **Time**: store UTC (`USE_TZ=True`), `TIME_ZONE="Asia/Dhaka"`, display in Dhaka time.
  Bookings use a `DateTimeRangeField` + Postgres exclusion constraint against overlap per ground.
- **IDs**: UUID primary keys on all domain models exposed via API.
- **Permissions**: DRF permission classes in `apps/<app>/permissions.py`; object-level
  checks for owner/staff/leader. Roles are permissions on one account, never separate user types.
- **API**: REST under `/api/v1/`, documented with drf-spectacular; after changing the API,
  regenerate frontend types (`npm run gen:api`). Paginate all list endpoints.
- **Configurable rules** (cutoff hours, auto-confirm windows, rating weights) live in
  `config/settings` constants or a `PlatformSetting` model — never hard-coded inline.
- **i18n**: every user-facing frontend string goes through next-intl; add keys to both
  `messages/en.json` and `messages/bn.json` (bn may be an English placeholder until
  Phase 11). Key sets must match — a unit test enforces it. Locale lives in the
  `NEXT_LOCALE` cookie; URLs carry **no** locale prefix (DECISIONS D13).
- **Next.js 16 specifics** (older tutorials get these wrong):
  - Request middleware is `src/proxy.ts`, not `middleware.ts`, and runs on the Node
    runtime only. It attaches the Clerk session and nothing else.
  - Protect routes at the resource with `await auth.protect()` in the route-group layout —
    `createRouteMatcher` is deprecated (DECISIONS D12).
  - `cookies()`, `headers()`, `params` and `searchParams` are **async**; `auth()` too.
  - `ClerkProvider` goes inside `<body>`; use `<Show when="signed-in">` wrapped in
    `<Suspense>`, not `<SignedIn>`.
  - `next lint` is removed — scripts call `eslint .` directly.
  - Tailwind 4 is CSS-first: no `tailwind.config.js`, theme lives in `globals.css`.
- **Email**: use Django's `MAILERS` setting, never the deprecated `EMAIL_*` settings —
  Django raises `ImproperlyConfigured` if both are present (DECISIONS D18).
- **Tests**: every service function gets tests; every phase ends with green
  `pytest` + `npm run lint && npm run typecheck` + its e2e happy path.
- Don't add libraries beyond the stack without noting why in `docs/DECISIONS.md`.

## Commands
```
./scripts/dev.sh                          # everything: infra + migrate + api + worker + web
./scripts/dev.sh --backend                # API only (see --help for more)

docker compose up -d                      # postgres (55432) + redis (56379)
cd backend && uv run python manage.py runserver
cd backend && uv run python manage.py seed_demo
cd backend && uv run pytest               # add --create-db after changing migrations
cd backend && uv run ruff check . && uv run ruff format .
cd backend && uv run celery -A config worker -B -l info
cd frontend && npm run dev
cd frontend && npm run lint && npm run typecheck && npm run format:check
cd frontend && npm run test               # Vitest
cd frontend && npm run test:e2e           # Playwright (needs real Clerk keys)
cd frontend && npm run gen:api            # regenerate API types (backend must be running)
```

**Environment notes (Phase 00):**
- Python 3.14 via `uv` (pinned in `.python-version`); Node 24 (`.nvmrc`).
- `brew install gdal` is required: GeoDjango loads GEOS/GDAL via `ctypes`, so importing
  any model with a `PointField` fails without them even though PostGIS runs in Docker.
- Container ports are **55432 / 56379**, not the defaults — a native Postgres and Redis
  occupy 5432/6379 on the dev machine and would silently shadow them.
- Local PostGIS image is `imresamu/postgis` (multi-arch); `postgis/postgis` is amd64-only
  and does not run on Apple Silicon. CI uses the upstream image. See DECISIONS D16.

## Working rhythm per phase
1. Read the phase file, DOMAIN.md sections it references, and PROGRESS.md.
2. Propose a short plan; then implement backend (models → services → API → tests),
   then frontend, then e2e.
3. Run all checks. Fix until green.
4. Update `docs/PROGRESS.md` (what was built, deviations, follow-ups) and commit.
