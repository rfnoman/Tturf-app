# Phase 02 — Turfs, Grounds, Pricing, Discovery

**Goal:** an owner registers a turf with location, grounds, hours and prices; admin approves;
players find turfs near them and see available slots.
**Depends on:** 01. **Domain refs:** §1 (owner/staff), §4.

## Steps
1. **Models** (`apps/turfs`)
   - `Turf` (owner via membership, name, slug, description, address, area, city, `location` PointField,
     phone, amenities (ArrayField or M2M `Amenity`), status machine draft → pending_review →
     approved | rejected | suspended, rejection_reason, `auto_confirm_enabled`, `cancellation_free_hours`).
   - `TurfPhoto` (image upload — local storage in dev, S3-compatible in prod via django-storages; set up the
     abstraction now).
   - `TurfMembership` (turf, user, role=owner|manager|cashier, invited_by, status=invited|active|removed).
   - `Ground` (turf, name, surface, sport formats M2M, max_players, slot_minutes, is_active).
   - `OperatingHours` (turf, weekday, open_time, close_time; support closing after midnight),
     `Closure` (turf or ground, start, end, reason).
   - `PriceRule` (ground, weekdays array, start_time, end_time, price, label).
2. **Services**
   - `submit_turf_for_review`, `approve_turf`, `reject_turf`, `suspend_turf`.
   - `invite_staff(turf, email|phone, role)`, `accept_staff_invite`, `remove_staff`.
   - `validate_price_coverage(ground)` — ground activation fails if any open hour has no price.
   - `get_availability(ground, date)` → list of slots `{start, end, price, label, available}`
     (operating hours − closures − active bookings; bookings arrive in Phase 03, write the selector so it
     already queries them via an interface).
3. **API**
   - Owner: CRUD turfs/grounds/hours/closures/prices/photos, submit for review, staff management.
   - Admin: review queue, approve/reject/suspend.
   - Public: `GET /turfs?near=lat,lng&radius_km=&sport=&area=&date=` (approved only, distance-sorted,
     PostGIS `Distance`), `GET /turfs/{slug}`, `GET /grounds/{id}/availability?date=`.
   - Permission classes: `IsTurfOwner`, `IsTurfStaff(roles=...)`, `IsPlatformAdmin`.
4. **Frontend**
   - Owner area: "Register your turf" multi-step form (details → location picker on a map → photos →
     grounds → hours → prices with a weekly grid editor → submit). Turf dashboard listing grounds and status.
     Staff management page.
   - Admin: turf review queue with approve/reject.
   - Player: turf discovery page (list + map toggle, filters by sport/area/date, "near me" via browser
     geolocation), turf detail page with photos, amenities, grounds and a date picker showing slots + prices.
   - Map: Leaflet + OpenStreetMap tiles (free) — note the choice in DECISIONS.md; can switch to Google Maps later.
5. **Tests:** price coverage, availability slicing (incl. after-midnight close), geo search ordering,
   permissions (staff of turf A can't edit turf B), status transitions.

## Acceptance checklist
- [ ] Owner registers a turf with 2 grounds and prices; submits; admin approves.
- [ ] Unapproved turfs never appear in public endpoints.
- [ ] Player near Mirpur sees Mirpur turfs first; slot grid shows correct prices for peak/night.
- [ ] Owner invites a cashier who can sign in and see (but not edit) the turf.

## Prompt for Claude Code
```
Start Phase 02. Read CLAUDE.md, docs/DOMAIN.md §1 and §4, docs/DECISIONS.md, docs/PROGRESS.md
and docs/phases/02-turfs-grounds.md.

Implement turfs, grounds, staff memberships, operating hours, closures, price rules, admin
review, PostGIS "near me" search and the availability selector, plus the owner registration
flow, admin review queue and player discovery/detail pages with a Leaflet map. Write the
availability selector so Phase 03 bookings plug in without rewriting it. Handle turfs that
close after midnight.

Seed 5 demo turfs in different Dhaka areas with realistic BDT prices. Tests first for
services/selectors. Run all checks, update PROGRESS.md and DECISIONS.md (map choice).
Present a plan first.
```
