# Phase 11 — audit and prioritised checklist

Written 2026-11-04, before any Phase 11 work, against `main` at the Phase 10 merge.
The point of writing it first is to stop "hardening" from becoming whatever was easiest
to reach for: everything below is something that is missing or wrong **now**, with the
reason it matters and what it blocks.

Facts it is built on: 167 API routes, 1310 backend tests, 105 Playwright tests, 950
translation keys, 24 declared indexes across 10 apps.

## Blocking launch

| # | Finding | Why it matters | Step |
|---|---|---|---|
| B1 | **707 of 950 `bn.json` keys are still the English string.** 257 keys carry Bengali script — the rest are placeholders from the phases that added them. | The app ships in Bangladesh. A Bangla toggle that returns English for three quarters of the UI is worse than no toggle, because it reads as broken rather than untranslated. | 1 |
| B2 | **No rate limiting anywhere.** `DEFAULT_THROTTLE_CLASSES` is unset and no view declares one. | Join requests, invites, conduct reports, player search and the Clerk webhook are all unmetered. A single script can fill a player's inbox, flood the admin conduct queue, or walk the whole player directory. | 4 |
| B3 | **No permission matrix test.** 167 routes, seven distinct `permission_classes` combinations, and nothing asserts that an endpoint refuses the roles it should. | Every phase added routes by hand. The failure mode is silent: one missing `IsAuthenticated` is a data leak nobody notices until it is in the logs. | 4 |
| B4 | **No PWA manifest and no icons.** `public/` holds the Next.js starter SVGs and `sw.js` (push only). | DOMAIN assumes a phone-first market; "add to home screen" is how an app without an app-store listing gets opened twice. | 2 |
| B5 | **No Sentry, no structured logging, no uptime check.** | A booking that fails for one player on one phone is invisible. Launch without this and the first week's bugs are reported as "it didn't work". | 5 |
| B6 | **No Dockerfile, no production compose, no deploy step.** CI runs tests and stops. | Nothing is deployable, so step 9's "full e2e against staging" has no staging. Needs a hosting decision first (D11, and the phase brief asks me to ask). | 8 |
| B7 | **No terms, privacy, refund or cancellation pages.** | Taking money (Phase 10) without a published refund policy is not a defensible position, and SSLCommerz merchant onboarding asks for the URLs. | 7 |

## Should fix before launch

| # | Finding | Why it matters | Step |
|---|---|---|---|
| S1 | **No query-count tests on hot endpoints.** The match board, store home, turf detail and the profile card all build nested payloads; nothing pins their query count, so an N+1 can be added without a single test turning red. | 3 |
| S2 | **Phone numbers are readable by anyone who can see a match or booking.** DOMAIN's PII line is that a number appears once two people are actually connected. | 4 |
| S3 | **Tunable rules are settings constants, so changing one is a deploy.** CLAUDE.md allows either, and named `PlatformSetting` rows as the other option; cutoffs and commission defaults are exactly the numbers a business wants to move on a Tuesday. | 5 |
| S4 | **No CSP.** HSTS, nosniff and `X-Frame-Options: DENY` are set; a content policy is not, and the frontend loads Leaflet tiles and Clerk from third-party origins, so it needs writing rather than copying. | 4 |
| S5 | **No dependency audit in CI** (`pip-audit`, `npm audit`). | 4 |
| S6 | **No admin business dashboard.** The pieces exist per queue (turfs, conduct, orders, finance) but there is no bookings/day, GMV, or no-show number anywhere — the things that say whether the pilot worked. | 6 |
| S7 | **Bangla typography is unset.** No Bengali font is loaded, so Bangla renders in whatever the device falls back to, and the digits are Western. | 1 |
| S8 | **No daily backup or tested restore.** | 5 |

## Already in good shape (checked, not assumed)

- **Permission intent is consistent**: `IsPlatformAdmin` checks `is_authenticated` itself,
  so the two views that declare it alone are not a hole — B3's test will prove it rather
  than leaving it to reading.
- **Pagination** is on every list endpoint (CLAUDE.md rule, enforced since Phase 02).
- **Indexes** exist where the phases that needed them added them, including the GiST
  exclusion constraint on bookings and composite status+time indexes; S1's query tests
  will show whether any are missing rather than guessing.
- **Secrets are all in env** with `.env.example` documenting every one as of Phase 10.
- **Money is `Decimal` throughout**, and the ledger cannot be written out of balance (D58).
- **Production security settings** (SSL redirect, HSTS a year with preload, nosniff,
  `X_FRAME_OPTIONS=DENY`, proxy SSL header) are already in `settings/prod.py`.

## Order of work

Bangla first (B1, S7) because it is the largest body of work and the one a native-speaker
review has to queue behind. Then PWA (B4), performance tests (S1), security (B2, B3, S2,
S4, S5), observability (B5, S3, S8), admin tools (S6), legal (B7), and deployment (B6)
last — it is the only step that needs a decision from you.
