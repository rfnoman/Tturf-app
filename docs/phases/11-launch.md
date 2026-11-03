# Phase 11 — Hardening, Bangla, PWA, Launch

**Goal:** production-ready: full Bangla, installable on phones, secure, observable, deployed,
with admin tools to run the business.
**Depends on:** all previous phases. **Decisions:** D11.

## Steps
1. **Bangla & localisation**: translate all `bn.json` keys (review by a native speaker), Bangla digits option,
   BDT formatting (৳), dates in Bangla, translated notification/email templates, Bangla-friendly font (e.g. Hind Siliguri /
   Noto Sans Bengali). Sport and product names support bn translations (`name_bn` fields or django-modeltranslation).
2. **PWA**: manifest, icons, service worker (already used for push), offline fallback page, "Add to home screen" prompt;
   test on low-end Android over slow 3G/4G.
3. **Performance**: query audit (django-debug-toolbar / `assertNumQueries` on hot endpoints: match board, store home,
   profile), DB indexes (GiST on locations and time ranges, composite indexes on status+time), Redis caching for
   public turf pages and leaderboards, image optimisation (Next/Image + resized uploads), pagination everywhere.
4. **Security**: permission audit test (every endpoint × role matrix), rate limiting (DRF throttling) on join requests,
   invites, reports, auth webhooks; upload validation; CORS/CSRF/headers (HSTS, CSP); secrets in env; dependency
   audit (pip-audit, npm audit); admin behind 2FA; PII minimisation (phone numbers hidden until a booking/match links people).
5. **Observability & ops**: Sentry (frontend + backend + Celery), structured logging, uptime checks, Celery monitoring
   (Flower or equivalent), daily DB backups with a tested restore, `PlatformSetting` admin for tunable rules.
6. **Admin & support tools**: dashboard (bookings/day, GMV, active players, top turfs, no-show rate), user lookup,
   impersonation-free support views, dispute/conduct/refund queues in one place, CSV exports.
7. **Legal & content**: terms, privacy policy, refund/cancellation policy pages, turf owner agreement, cookie notice.
8. **Deployment (D11)**: Dockerfiles for backend/worker/beat, production compose or platform config, managed Postgres with
   PostGIS, Redis, media on S3-compatible storage, frontend on Vercel, staging + production environments, CI/CD deploy
   on merge to `main` with migrations step, Clerk production instance and domains.
9. **Launch checks**: full e2e suite on staging (the journeys below), load test the match board and booking create,
   seed real turfs with owners for a pilot area (e.g. Mirpur/Dhanmondi).

## End-to-end journeys that must pass on staging
1. Owner registers turf → admin approves → owner adds staff and inventory.
2. Player onboards → books publicly → others request → approved → teams set → scorecard → confirm → MOTM → ratings update.
3. Squad (closed) books → member proposes outsider found in search → leader approves → player accepts → plays.
4. Player with a match tomorrow orders from platform before cutoff → delivered to turf → appears on match page.
5. Player orders home delivery from platform; picks up a turf item; staff sells at counter; stock is consistent.
6. Advance payment online → late cancellation → advance forfeited, ledger correct.
7. Entire journey 2 in Bangla on a mobile viewport.

## Prompt for Claude Code
```
Start Phase 11. Read CLAUDE.md, docs/DECISIONS.md (D11), docs/PROGRESS.md and
docs/phases/11-launch.md.

Work through the steps in order, one step per session if needed, and ask me before choosing a
hosting provider. Begin with a written audit (performance, security permission matrix,
missing translations) and a prioritised checklist, then implement. Finish by making the seven
end-to-end journeys pass as Playwright tests against staging. Update PROGRESS.md after each step.
Present a plan first.
```
