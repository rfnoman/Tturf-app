# Decisions Log

Defaults chosen so building can start. **The product owner can change any of these** — edit
the entry, mark it `REVISED`, and tell Claude Code which phases to adjust.

| ID | Question | Decision (default) | Affects |
|---|---|---|---|
| D1 | Closed group: when a member adds a player, does the leader approve? | **Yes.** Member proposes → leader approves → player accepts. Leader's own invites skip approval. | Phase 4 |
| D2 | Are individual bookings always public? | **No.** Booker chooses `public` (looking for players, shows "need X") or `private`. Default public. | Phase 4 |
| D3 | Cash booking confirmation | **Hybrid.** Auto-confirm if player has ≥3 completed bookings and reliability ≥ 80 and turf allows auto-confirm; otherwise owner/staff must confirm within 2h (or before 1h to start, whichever is sooner) or the reservation expires. Turf can switch to "always manual". | Phase 3 |
| D4 | Home delivery of turf inventory | **v1: pickup only** for turf stock. Later option (flag `turf_delivery_enabled`): platform rider collects from turf. | Phase 8 |
| D5 | 16h cutoff for platform → turf delivery | Global setting `TURF_DELIVERY_CUTOFF_HOURS=16`, overridable per `DeliveryZone`. | Phase 8 |
| D6 | Live scoring | **Final score first** (Phase 5). Live scoring is an optional step at the end of Phase 5 behind a feature flag. | Phase 5 |
| D7 | Staff verification of scorecards | **Optional** upgrade; gives "Verified" badge and ×1.5 rating weight. | Phase 5–6 |
| D8 | Online payments | SSLCommerz (cards + wallets) first, bKash direct later if needed. Advance = turf-configurable % (default 25%). | Phase 10 |
| D9 | Phone sign-in | **RESOLVED (Phase 00).** Email + Google sign-in for v1; `User.phone` is an unverified profile field. See the D9 note below. | Phase 0, 1 |
| D10 | Python tooling | `uv` for dependency management. | Phase 0 |
| D11 | Hosting (proposal) | Frontend on Vercel; backend + Celery + Postgres/PostGIS + Redis on a managed platform or VPS (Docker). Final choice in Phase 11. | Phase 11 |

## Phase 00 additions

| ID | Question | Decision | Affects |
|---|---|---|---|
| D12 | Clerk route protection | **Resource-level.** `src/proxy.ts` runs bare `clerkMiddleware()` to attach the session; each route-group layout calls `await auth.protect()`. Next 16 renamed `middleware.ts` to `proxy.ts` (Node runtime only, no `edge`), and Clerk deprecated `createRouteMatcher` after the 2025 middleware-bypass disclosures, recommending gating as close to the data as possible. The backend re-checks permissions on every endpoint regardless. | All frontend phases |
| D13 | Locale in the URL | **No locale prefix.** `/bookings` stays `/bookings`; the choice lives in a `NEXT_LOCALE` cookie set by a server action. Keeps route groups flat across eleven phases and leaves Clerk's proxy untouched. Cost: one URL per page, so Bangla pages are not separately shareable or indexable. Revisit in Phase 11 if SEO demands it. | All frontend phases |
| D14 | Next.js Cache Components | **Off** (`cacheComponents: false`). Almost every page renders per-user authenticated data (bookings, matches, profile), where caching buys little and the Suspense requirements add friction to every phase. Phase 11's performance step revisits it with real pages to measure. | All frontend phases |
| D15 | Clerk JWT verification in Django | **Hand-rolled `PyJWT` + cached JWKS**, not the official `clerk-backend-api` SDK. Matches the brief, keeps JWKS mockable so the auth class is fully unit-tested without network access, and adds no dependency. The SDK (7.1.0, released 2026-11-02) ships no Django example. Revisit if Clerk's token semantics shift. | Phase 00+ |
| D16 | Local PostGIS image | **`imresamu/postgis:17-3.6`** for local development. The canonical `postgis/postgis` images are **amd64-only** and will not run on Apple Silicon without emulation; `imresamu` is the multi-arch build of the same upstream docker-postgis Dockerfiles. CI runs on amd64 runners and uses `postgis/postgis:17-3.6`. Override with `POSTGIS_IMAGE`. | Local dev, CI |
| D17 | Django version | **6.1.x** (latest stable) over 5.2 LTS, per the brief's "latest stable" instruction. Verified in Phase 00: DRF 3.18.3 is required (the `cc_delim_re` import crash on 6.1 was a DRF bug), and drf-spectacular 0.30.0 generates the schema cleanly under `--fail-on-warn` despite only declaring support up to Django 6.0. 6.1 is supported to Dec 2027; 6.2 LTS lands Apr 2027. | Backend |
| D18 | Email sending | **`MAILERS`**, not the flat `EMAIL_*` settings. Django 6.1 deprecated `EMAIL_BACKEND` and friends (removal in Django 2028) and raises `ImproperlyConfigured` if both are set, so Phase 03's notifications are built on `MAILERS` from the start. | Phase 03+ |

## Phase 01 additions

| ID | Question | Decision | Affects |
|---|---|---|---|
| D19 | Where does the player profile live? | **A new `apps/players`**, not `apps/accounts`. `accounts` mirrors Clerk and is overwritten by the webhook on every change; the profile is ours and must not be clobbered by a sync. The phase file sanctioned either. CLAUDE.md's repository layout did not list `players` — this entry is the amendment. | Phase 01+ |
| D20 | How does the frontend learn business rules (rating caps, cutoffs)? | **`GET /api/v1/config`**, public and unauthenticated. CLAUDE.md forbids hard-coding configurable rules, and that has to hold on both sides of the wire — an onboarding slider whose ceiling is a literal silently disagrees with `SELF_ASSESSED_RATING_CAP` the moment anyone changes it. Reads through `apps/core/utils.setting`, so the `PlatformSetting` model will be picked up with no frontend change. | All frontend phases |
| D21 | Identity for an account created from a session token | **Lazy backfill from Clerk's Backend API.** A Clerk session token carries no identity claims (`sub`, `sid`, `iss`, `azp`, `exp` only — verified against the live instance), so a row created on first authenticated request has no name or email. The webhook is the normal sync path but has no public URL in local development, leaving every account showing as "Player". `get_or_create_user_from_claims` therefore reads the user once, only when `last_synced_at` is NULL, and stamps the timestamp even on failure — at most one request per account, and a Clerk outage never blocks sign-in. | Phase 00+ |
| D22 | Overall rating before the Phase 06 engine | Weighted mean of the sport's skills (`OVERALL_SKILL_SHARE`, 0.65) blended with the player's shared attributes weighted per sport (`OVERALL_ATTRIBUTE_SHARE`, 0.35). Skills with `counts_toward_overall=False` — goalkeeping, wicket keeping — are excluded so an outfielder is not dragged down by a skill only keepers rate. Either half may be missing, in which case the other carries the whole weight. Deterministic and written **only** by `refresh_sport_rating`, so Phase 06 can replace it in one place. | Phase 01, 06 |
| D23 | Authenticated end-to-end tests | **`@clerk/testing` with a disposable Clerk user per run**, signed in through `clerk.signIn`'s *email* overload (a Backend-API sign-in token redeemed with the `ticket` strategy). Onboarding is by definition a once-per-account flow, so a fixed test account would pass once and fail forever after. The ticket strategy is required rather than preferred: the password strategy stops at Clerk's new-device email verification, and the helper's password branch calls `setActive` with a null session id instead of raising — a failed sign-in then looks like a pass. Specs skip when Clerk is unconfigured, so a bare checkout still runs the public smoke suite. | Phase 01+ |

## Phase 02 additions

| ID | Question | Decision | Affects |
|---|---|---|---|
| D24 | Maps | **Leaflet + OpenStreetMap tiles**, as the phase file proposed. Free, no API key, no per-load billing, and the OSM data for Dhaka is good enough to place a turf. Driven through Leaflet's imperative API rather than react-leaflet so the map is one client boundary with no extra wrapper library. Switching to Google Maps later means replacing one component. **Leaflet reads `window` at module scope**, which `"use client"` does not prevent — Next still evaluates client modules on the server for the initial HTML — so it is loaded through `next/dynamic` with `ssr: false` in `components/turf/turf-map.tsx`; importing the implementation directly is a 500. Its default marker PNG is resolved relative to Leaflet's own CSS and no bundler rewrites it, so markers are an inline-SVG `divIcon`. | Phase 02+ |
| D25 | How do Phase 03 bookings reach the availability selector? | **A provider registry** in `apps/turfs/availability.py`. `apps.turfs` must not import `apps.bookings` (the dependency runs the other way), so availability asks a list of registered callables for the ranges already taken; Phase 03's `AppConfig.ready()` registers one. Until then the list is empty and every open slot reads as free. Satisfies the phase brief's "write the selector so it already queries them via an interface" without a circular import or a rewrite later. | Phase 02, 03 |
| D26 | Which slot does a price rule apply to? | **The band the slot *starts* in.** A 90-minute booking that straddles the peak boundary keeps the price it was quoted; repricing halfway through would make the displayed price a lie. Where several rules match, the **most specific wins**: fewer weekdays beats more, then a shorter window beats a longer one — so a turf keeps one broad "all week" rule and overrides Friday nights without reordering anything. | Phase 02, 03 |
| D27 | Turfs that close after midnight | **`close_time <= open_time` means the window crosses midnight**, and equal times mean a full 24 hours. 18:00–02:00 is a normal Dhaka evening, so availability for a date includes both that date's own window *and* the tail of the previous day's. Price coverage follows the same rule, which is why the 00:00–02:00 tail needs a price on the **following** weekday. | Phase 02, 03 |
| D28 | Who sees a ground that is not bookable? | **Owners and reviewing admins, never players.** A ground is created inactive and only becomes bookable once its open hours are fully priced, so hiding inactive grounds from the owner would hide the exact row they have to price and activate. The public selector still filters them out. (Found in Phase 02 by driving the owner flow in a browser; the API tests had only ever built active grounds.) | Phase 02+ |

### D9 — phone sign-in for Bangladesh (+880)

Resolved from Clerk's current documentation. What is **confirmed**:

- Clerk's SMS allowlist enables **only the US and Canada by default**. A disabled country
  cannot receive OTPs *or be used at sign-up at all* — so with +880 off, Bangladeshi phone
  sign-up is fully blocked, not merely degraded. Toggle: Dashboard → SMS → Settings.
- **Phone authentication requires a paid plan in production** (development instances can
  test it free).
- Countries sit in tiers A–F gated on a `phone_code` plan feature. Removing a tier B–F
  country from the blocklist on a free/dev instance fails with
  `SMSCountryRemovalRestricted`, "to prevent SMS pumping abuse".
- No current Clerk documentation offers a bring-your-own-Twilio escape hatch.

What is **not published**: which tier +880 is in, and the per-message cost for Bangladesh
("international at market rate"). Tier A appears to be the default-enabled US/CA set, so
+880 is very likely tier B–F and therefore plan-gated — likely, but unverified.

**Decision:** v1 uses email + Google sign-in, with `phone` as an unverified field on the
profile. Follow-ups before any SMS commitment: (1) try toggling Bangladesh on a dev
instance and see whether it is plan-blocked, (2) ask Clerk support in writing for the
+880 tier and per-message rate.
