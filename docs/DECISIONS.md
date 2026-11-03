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
