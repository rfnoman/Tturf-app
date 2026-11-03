# TurfApp

A platform for sports turfs in Bangladesh. Turf owners list grounds and sell inventory;
players book grounds (solo or as a squad), fill matches with other players, record
scorecards and build a FIFA-style profile. A platform store delivers fitness products to
the turf or to the player's home.

- **Business rules:** [`docs/DOMAIN.md`](docs/DOMAIN.md) (source of truth)
- **Decisions:** [`docs/DECISIONS.md`](docs/DECISIONS.md)
- **Roadmap:** [`docs/PLAN.md`](docs/PLAN.md) · phase files in [`docs/phases/`](docs/phases)
- **What exists today:** [`docs/PROGRESS.md`](docs/PROGRESS.md)
- **Conventions for contributors (and Claude Code):** [`CLAUDE.md`](CLAUDE.md)

## Stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 16 (App Router) + TypeScript, Tailwind 4, shadcn/ui, TanStack Query, next-intl (en + bn) |
| Auth | Clerk — `@clerk/nextjs` on the frontend; Django verifies Clerk session JWTs via JWKS |
| Backend | Django 6.1 + DRF, drf-spectacular (OpenAPI) |
| Database | PostgreSQL 17 + PostGIS 3.6 (`django.contrib.gis`) |
| Jobs | Celery + Redis |
| Tests | pytest-django + factory_boy, Vitest, Playwright |

## Prerequisites

| Tool | Version | Install |
|---|---|---|
| Docker | any recent | `colima start` (this machine uses Colima) |
| uv | ≥ 0.11 | `brew install uv` — manages Python 3.14 itself |
| Node | 24 LTS | `brew install node@24 && brew link --overwrite node@24` |
| GDAL / GEOS / PROJ | GDAL ≥ 3.3 | `brew install gdal` (pulls geos and proj) |

GDAL and GEOS are **not optional**. GeoDjango loads them through `ctypes`, so importing
any model with a `PointField` fails without them — even though PostGIS itself runs in
Docker. On Apple Silicon `ctypes` does not search `/opt/homebrew/lib`, so
`config/settings/base.py` points at the Homebrew dylibs explicitly; override with
`GDAL_LIBRARY_PATH` / `GEOS_LIBRARY_PATH` if your paths differ.

To go back to Node 20: `brew unlink node@24 && brew link --overwrite node@20`.

## Setup

First time only:

```bash
cd backend  && cp .env.example .env && uv sync && cd ..
cd frontend && cp .env.local.example .env.local && npm install && cd ..
```

Then fill in the Clerk values (next section) and run everything with one command:

```bash
./scripts/dev.sh
```

That starts Colima if Docker is down, brings up Postgres and Redis and waits for them
to report healthy, applies migrations, then runs Django, the Celery worker+beat and
Next.js together with each service's output prefixed and mirrored to `.logs/`. Ctrl+C
stops everything it started; the containers are left running on purpose.

```bash
./scripts/dev.sh --backend       # API only
./scripts/dev.sh --no-worker     # skip Celery (nothing schedules work until Phase 03)
./scripts/dev.sh --no-infra      # Postgres and Redis are already up
./scripts/dev.sh --help          # all options
docker compose down              # stop the containers too
```

<details>
<summary>Running the pieces by hand instead</summary>

```bash
docker compose up -d                                   # postgres + redis
cd backend  && uv run python manage.py migrate
cd backend  && uv run python manage.py runserver       # http://127.0.0.1:8000
cd backend  && uv run celery -A config worker -B -l info
cd frontend && npm run dev                             # http://localhost:3000
```

</details>

Seed demo data once the database is up: `cd backend && uv run python manage.py seed_demo`.

Ports: the containers publish **55432** (Postgres) and **56379** (Redis) rather than the
defaults, because a native Postgres and Redis already occupy 5432/6379 on this machine
and would silently shadow them. Override with `POSTGRES_PORT` / `REDIS_PORT`.

Useful URLs once both are running:

| URL | What |
|---|---|
| http://127.0.0.1:8000/api/v1/health | Liveness, reports the PostGIS version |
| http://127.0.0.1:8000/api/v1/docs/ | Swagger UI |
| http://127.0.0.1:8000/api/v1/schema/ | OpenAPI schema (source for `npm run gen:api`) |
| http://127.0.0.1:8000/admin/ | Django admin (`seed_demo` creates `admin` / `admin`) |
| http://localhost:3000/me | Debug page showing Django's `/api/v1/me` response |

## Clerk setup — the environment variables you must fill in

Nothing runs without these: `@clerk/nextjs` refuses to initialise without a publishable
key. Create an application at <https://dashboard.clerk.com>, then:

### 1. Sign-in methods

Enable **Email** and **Google**. Leave phone/SMS off for now — see `DECISIONS.md` D9:
Clerk's SMS allowlist enables only the US and Canada by default, phone auth needs a paid
plan in production, and enabling tier B–F countries (which includes +880) is plan-gated.
`User.phone` exists as an unverified profile field instead.

### 2. Keys — Dashboard → **API keys**

| Variable | File | Value |
|---|---|---|
| `NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY` | `frontend/.env.local` | `pk_test_…` (safe in the browser) |
| `CLERK_SECRET_KEY` | `frontend/.env.local` **and** `backend/.env` | `sk_test_…` — never expose this |
| `CLERK_FRONTEND_API_URL` | `backend/.env` | The **Frontend API URL** on the same page, e.g. `https://<slug>.clerk.accounts.dev`. JWKS is this plus `/.well-known/jwks.json` |
| `CLERK_ISSUER` | `backend/.env` | Same value — Django verifies it as the token's `iss` claim |
| `CLERK_AUTHORIZED_PARTIES` | `backend/.env` | `http://localhost:3000,http://127.0.0.1:3000` — the `azp` allowlist |

### 3. Webhook — Dashboard → **Webhooks** → *Add Endpoint*

| Field | Value |
|---|---|
| Endpoint URL | `https://<public-url>/api/v1/webhooks/clerk` |
| Events | `user.created`, `user.updated`, `user.deleted` |
| Signing Secret | Reveal it (eye icon) → `CLERK_WEBHOOK_SIGNING_SECRET` in `backend/.env` |

Clerk must reach the endpoint over the public internet, so local testing needs a tunnel
(`cloudflared tunnel --url http://localhost:8000`, ngrok, or similar). The webhook is not
on the critical path: `ClerkJWTAuthentication` also creates the `User` row on the first
authenticated API call, so sign-in works before the webhook is wired up.

## Commands

```bash
docker compose up -d                                 # postgres + redis
docker compose down                                  # stop (volumes survive)

cd backend
uv run python manage.py runserver
uv run python manage.py seed_demo                    # demo data, idempotent
uv run pytest                                        # add --create-db after migrations change
uv run ruff check . && uv run ruff format .
uv run celery -A config worker -B -l info            # worker + beat

cd frontend
npm run dev
npm run lint && npm run typecheck && npm run format:check
npm run test                                         # Vitest
npm run test:e2e                                     # Playwright (needs real Clerk keys)
npm run gen:api                                      # regenerate API types (backend must be running)
```

## Repository layout

```
turf-app/
  backend/            Django project (uv)
    config/           settings/{base,dev,test,prod}, urls, celery
    apps/core/        abstract bases, health, extensions migration, seed_demo
    apps/accounts/    User, Clerk JWT auth, Clerk webhook, /me
  frontend/           Next.js app
    src/app/          routes: (player), (owner), (admin), sign-in, sign-up, me
    src/lib/api/      generated OpenAPI types + typed client
    src/i18n/         cookie-based locale config, request handler, switcher action
    messages/         en.json, bn.json
    e2e/              Playwright specs
  docs/               DOMAIN, DECISIONS, PLAN, PROGRESS, phases/
  .github/workflows/  backend and frontend CI
```

## Conventions worth knowing before you edit

- Business logic goes in each app's `services.py`; read-heavy queries in `selectors.py`.
  Views and serializers stay thin.
- State machines are explicit: one service function per transition, validating the
  from-state and writing an event row. Never assign `status` directly elsewhere.
- Money is `Decimal(max_digits=12, decimal_places=2)` in BDT. Never floats.
- Times are stored in UTC and displayed in Dhaka time.
- Every user-facing string goes through next-intl, with keys in **both** `en.json` and
  `bn.json` (Bangla may be an English placeholder until Phase 11).
- After changing the API, run `npm run gen:api`.
