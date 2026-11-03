# Phase 03 — Bookings & Cash Payment

**Goal:** a player books a slot; the system prevents double booking; owner/staff confirm,
collect cash, and mark no-shows; everyone gets notifications.
**Depends on:** 02. **Domain refs:** §5, §11. **Decisions:** D3.

## Steps
1. **Models** (`apps/bookings`, `apps/payments`, `apps/notifications`)
   - `Booking` (ground, booked_by, sport, format, `time_range` DateTimeRangeField, price, mode=individual|group,
     squad (nullable, FK added in Phase 04 — leave nullable UUID or add FK later), visibility=public|private,
     status, confirmed_by, cancelled_by, cancel_reason, `expires_at`, notes).
   - **Exclusion constraint** with `btree_gist`: `ground WITH =, time_range WITH &&` where status in active set.
   - `BookingEvent` (booking, from_status, to_status, actor, note, created_at).
   - `Payment` (generic target via FK fields `booking` / later `order`, method=cash, amount, status=pending|paid|refunded,
     collected_by, collected_at).
   - `Notification` (user, type, title, body, data JSON, read_at) + `notify(user, type, **ctx)` service with
     templates per type; email sending via Django email backend (console in dev).
   - Player `reliability_score` updates via service.
2. **Services** (one per transition, all write `BookingEvent`)
   - `create_booking(player, ground, start, format, mode, visibility)` — validates slot is offered and priced,
     player has no overlapping booking, start is in the future and within the turf's booking horizon (e.g. 30 days).
     Applies D3: auto-confirm or `reserved` with `expires_at`. Catches the exclusion-constraint IntegrityError
     → "slot just taken".
   - `confirm_booking`, `expire_booking` (Celery beat every minute), `cancel_booking` (late-cancel rule from
     `cancellation_free_hours`), `mark_paid` (creates/updates cash Payment), `mark_no_show` (only after start + grace),
     `complete_booking` (auto after end time via Celery if paid).
   - `update_reliability(player, event)` with configurable deltas.
3. **API**
   - Player: `POST /bookings`, `GET /me/bookings?upcoming|past`, `POST /bookings/{id}/cancel`.
   - Staff/owner: `GET /turfs/{id}/bookings?date=` (calendar), `POST /bookings/{id}/confirm|mark-paid|no-show|cancel`,
     walk-in booking for a phone number (creates booking on behalf).
   - Notifications: `GET /me/notifications`, `POST /me/notifications/read`, unread count.
   - Availability endpoint from Phase 02 now excludes active bookings.
4. **Frontend**
   - Booking flow: from turf detail slot grid → choose format, mode (individual/group placeholder),
     public/private → review (price, cancellation policy, "pay cash at turf") → confirm → booking page
     showing status timeline.
   - My bookings (upcoming/past) with cancel.
   - Owner/staff: day/week calendar per ground (colour by status), booking drawer with actions,
     "pending confirmation" queue with countdown, walk-in booking.
   - Notification bell with dropdown + page; poll every 30s (real-time comes later).
5. **Tests:** concurrency test (two parallel bookings for the same slot — exactly one succeeds), each
   transition's allowed/forbidden from-states, expiry job, late cancel affects reliability, D3 auto-confirm logic,
   staff of another turf forbidden.

## Acceptance checklist
- [ ] Two browsers booking the same slot at once: one succeeds, the other sees "slot just taken".
- [ ] New player's booking needs owner confirmation and expires if ignored.
- [ ] Reliable player's booking auto-confirms (when the turf allows it).
- [ ] Staff marks paid → completed after end time; no-show lowers reliability.
- [ ] Notifications arrive for confirm, cancel, expiry.

## Prompt for Claude Code
```
Start Phase 03. Read CLAUDE.md, docs/DOMAIN.md §5 and §11, docs/DECISIONS.md (D3),
docs/PROGRESS.md and docs/phases/03-bookings-cash.md.

Implement bookings with a Postgres exclusion constraint (btree_gist) so double booking is
impossible, the explicit booking state machine with BookingEvent history, cash payments,
reliability updates, Celery jobs for expiry/completion, and the notifications app. Build the
player booking flow, my-bookings page, owner/staff calendar with action drawer and pending
queue, and a notification bell.

Write the state-machine tests and a real concurrency test before the service code. Leave the
squad link ready for Phase 04. Run all checks, update PROGRESS.md. Present a plan first.
```
