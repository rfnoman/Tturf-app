# Phase 00 — Foundation

**Goal:** a monorepo where a user signs in with Clerk on the Next.js app, and the Django API
recognises them. All later phases build on this skeleton.
**Depends on:** nothing. **Domain refs:** §1 (roles, only the User part).

## Steps
1. **Repo & tooling**
   - `git init`, `.gitignore` (Python, Node, env files), `.editorconfig`, root `README.md`.
   - `docker-compose.yml`: `postgis/postgis` (Postgres 16) and `redis:7`, named volumes, healthchecks.
   - `.env.example` files for backend and frontend (no secrets committed).
2. **Backend skeleton** (`backend/`, managed with `uv`)
   - Django + DRF + drf-spectacular + django-cors-headers + psycopg + django-environ +
     celery + redis + PyJWT[crypto] + svix + pytest-django + factory_boy + ruff.
   - `config/settings/{base,dev,test,prod}.py`; `django.contrib.gis` enabled; `TIME_ZONE="Asia/Dhaka"`,
     `USE_TZ=True`; `LANGUAGES = en, bn`.
   - `apps/core`: `TimeStampedModel`, `UUIDModel` abstract bases; health endpoint `GET /api/v1/health`.
   - Celery app in `config/celery.py` with a sample task and beat schedule placeholder.
   - OpenAPI schema at `/api/v1/schema/` and Swagger UI at `/api/v1/docs/`.
3. **Clerk auth in Django** (`apps/accounts`)
   - Custom `User` model (`AUTH_USER_MODEL`) with `clerk_id` (unique), email, phone, first/last name,
     `image_url`, `is_platform_admin`. Created **before the first migration**.
   - DRF authentication class `ClerkJWTAuthentication`: reads `Authorization: Bearer <token>`,
     verifies against Clerk JWKS (cached), checks `iss`, `exp`, `azp` against allowed origins,
     gets or creates the User by `sub`.
   - Webhook `POST /api/v1/webhooks/clerk` verified with svix: handles `user.created`,
     `user.updated`, `user.deleted` (soft-deactivate).
   - `GET /api/v1/me` returns the current user.
4. **Frontend skeleton** (`frontend/`)
   - Next.js (App Router, TypeScript, `src/`), Tailwind, shadcn/ui init, ESLint, Prettier.
   - `@clerk/nextjs`: `ClerkProvider`, middleware protecting everything except `/`, `/sign-in`, `/sign-up`.
   - next-intl with `en.json` + `bn.json`, language switcher in the header.
   - TanStack Query provider; `src/lib/api/client.ts` that attaches the Clerk token
     (`getToken()`) to each request; `npm run gen:api` using `openapi-typescript` against the backend schema.
   - Layout shell: header (logo, nav, user button, language switch), mobile-first responsive.
     Route groups `(player)`, `(owner)`, `(admin)` with placeholder pages.
   - `/me` debug page showing the backend `/me` response.
5. **Quality**
   - Backend: ruff config, pytest with a test DB using PostGIS; tests for the auth class (mock JWKS) and webhook.
   - Frontend: Vitest set up; Playwright set up with one smoke test (home page loads).
   - GitHub Actions: backend (ruff + pytest with postgis service) and frontend (lint, typecheck, build).
6. **Phone sign-in check (D9):** confirm whether Clerk's SMS sign-in works for +880 numbers on the
   current plan; record the result in `DECISIONS.md`.

## Acceptance checklist
- [ ] `docker compose up -d` then backend and frontend start with the documented commands.
- [ ] Sign up on the frontend → a `User` row exists in Django (via the webhook or first API call).
- [ ] `/me` page shows the Django user's data.
- [ ] Swagger UI lists `/health` and `/me`.
- [ ] CI passes on push.

## Prompt for Claude Code
```
We are starting Phase 00 of the TurfApp project. Read CLAUDE.md, docs/PLAN.md,
docs/DECISIONS.md and docs/phases/00-foundation.md.

Set up the monorepo exactly as described in Phase 00: docker compose (PostGIS + Redis),
the Django backend with uv, a custom User model and Clerk JWT authentication + svix-verified
Clerk webhook, the Next.js frontend with Clerk, next-intl (en/bn), TanStack Query, a typed
API client generated from the OpenAPI schema, test tooling and GitHub Actions CI.

Create the custom User model before the first migration. Use the latest stable versions of
every library and check their current docs for setup (especially Clerk + Next.js middleware
and Clerk JWT verification). Give me the list of environment variables I must fill in from
my Clerk dashboard and where to find each one.

Finish by running all checks, then update docs/PROGRESS.md and the Commands section of
CLAUDE.md if anything changed. Present a plan first.
```
