# Domain Rules — Source of Truth

Behaviour in code must match this file. If something is unclear or missing, check
`DECISIONS.md`; if it is not there either, ask, then record the answer in `DECISIONS.md`.

---

## 1. Roles
One account (synced from Clerk) can hold several roles at once.

| Role | Granted by | Can do |
|---|---|---|
| Player | Default on sign-up | Profile, book, join, score, rate, shop |
| Turf Owner | Registering a turf (admin approves the turf) | Manage own turfs, grounds, pricing, inventory, staff, bookings |
| Turf Staff | Invited by an owner to a specific turf | Confirm bookings, mark paid/no-show, counter sales, verify scorecards for that turf |
| Platform Admin | Django superuser / `is_platform_admin` | Approve turfs and sports, platform store, delivery, disputes, conduct reports |
| Rider | Admin assigns | See and update deliveries assigned to them |

Turf ownership and staff are modelled as `TurfMembership(user, turf, role=owner|manager|cashier)`.

## 2. Sports catalogue
- `Sport` is global and admin-curated. Owners **propose** a sport (`SportProposal`); an admin
  approves (creates the Sport) or merges it into an existing one. No duplicates.
- Each Sport defines:
  - `formats` (e.g. 5v5, 7v7, singles, doubles, nets) with `players_per_side`
  - `SportSkill` list (sport-specific skills, e.g. finishing, bowling)
  - weights for shared `Attribute`s (stamina, agility, speed, strength) used in overall rating
  - `StatDefinition` list (scorecard fields, see §7)
  - `met_value` for calorie estimation (§10)
- Grounds declare which sports/formats they support.

## 3. Player profile
- On onboarding the player selects sports (`PlayerSport`, `is_verified=False`) and gives a
  short self-assessment per sport (shown as "unverified" rating).
- A sport becomes **verified/unlocked** on the profile when the player completes a *locked*
  match of that sport. If they never selected it, it is added automatically.
- Shared attributes (stamina, agility, speed, strength) belong to the player, not the sport,
  and display on every sport card.
- Profile shows per sport: overall rating, skills, matches, wins, MOTM, sport stats,
  form (last 5), reliability, fair-play badge, grounds played.
- `discoverable` flag (default true) controls appearance in player search.
- `available_to_play` windows: player can post "free on <date/time range> in <area>".

## 4. Turfs, grounds, pricing
- `Turf`: name, description, address, `area` (e.g. Dhanmondi), `location` (PostGIS Point),
  photos, amenities (floodlights, parking, changing room, washroom, cafe), contact phone,
  `status` = draft → pending_review → approved | rejected | suspended.
- Only approved turfs are visible/bookable.
- `Ground` belongs to a Turf: name, surface, supported sport formats, `max_players`,
  `slot_minutes` (60/90/120), `is_active`.
- `OperatingHours` per turf per weekday; `Closure` for blackout dates/ranges.
- `PriceRule` per ground: weekday set, time range, price per slot, optional label
  (peak/off-peak/night). Most specific matching rule wins; a ground must have full coverage
  of its operating hours before it can be activated.
- Availability = operating hours − closures − existing active bookings, sliced by `slot_minutes`.

## 5. Bookings and payment
- A booking reserves one ground for one time range: `Booking(ground, booked_by, time_range,
  sport, format, price, mode, status)`.
- **Double booking is impossible at DB level**: exclusion constraint on
  `(ground, time_range)` for statuses in {reserved, confirmed, paid}.
- Modes: `individual` or `group` (linked to a Squad). See §6 for visibility.
- **Status machine**:
  `reserved → confirmed → paid → completed`
  `reserved → expired` (not confirmed in time; slot released)
  `reserved|confirmed → cancelled` (by player or owner, with reason)
  `confirmed → no_show` (marked by staff after start + grace)
- **Cash confirmation**: see DECISIONS D3 (auto-confirm for reliable players, otherwise owner/staff
  confirm within a window; unconfirmed reservations expire).
- **Cancellation policy** per turf: free until N hours before start; later cancellations count
  against reliability (and forfeit advance once online payments exist, Phase 10).
- `Payment(booking|order, method=cash|sslcommerz|bkash, amount, status, collected_by)`.
  Cash payment is recorded by staff when marking paid.
- **Reliability score** (0–100): starts at 100 for new players with confirmation by owner until
  3 completed bookings; decreases on no-show (−15) and late cancel (−5), recovers +2 per
  completed match, capped at 100. Exact numbers configurable.

## 6. Matches, squads, joining
- Every booking creates exactly one `Match` (roster lives on the match).
- `Squad`: persistent group with a `leader`, members, sports, `accepts_public_requests` default.
- `Match.visibility`:
  | Booking | Visibility | Who can get in |
  |---|---|---|
  | individual, public | on match board | anyone requests → booker approves |
  | individual, private | hidden | booker invites |
  | group, open (`accepts_public_requests=True`) | on match board | anyone requests → leader approves |
  | group, closed | squad only | any member proposes a player → leader approves → player accepts |
- `Match.capacity` = format players_per_side × 2 (or ground max). `needed = capacity − roster`.
  Requests/invites are blocked when full.
- `JoinRequest(match, player, message, status=pending|approved|declined|withdrawn|expired)`.
  Approval adds the player to the roster; if the match is a group match and the leader chooses,
  the player is also added to the squad.
- `MatchInvite(match, invited_player, invited_by, status=proposed|leader_approved|accepted|declined)`.
  Invites by the leader/booker skip `proposed`.
- Requests and invites expire at match start.
- **Match board**: list of public matches with filters (sport, area/near me, date, time,
  rating range, needed > 0) showing turf, ground, time, format, needed count, average rating.

## 7. Scoreboard
- Before kickoff the roster is split into Team A / Team B (manual or auto-balanced by rating);
  each team has a captain. Default scorer = booker/leader; can be reassigned to a captain or
  turf staff.
- `StatDefinition(sport, key, label, type=int|bool|decimal, scope=player|team, min, max)`
  e.g. football: goals, assists, saves, clean_sheet, yellow, red; cricket: runs, balls,
  wickets, overs, runs_conceded, catches; badminton: sets_won, points_won.
  All sports: `minutes_played`.
- `Scorecard(match, team_a_score, team_b_score, result, status, entered_by, verified_by_staff)`
  and `PlayerStat(scorecard, player, stat_definition, value)`.
- **Status machine**: `draft → submitted → confirmed → locked`, `submitted → disputed → (admin/staff
  resolves) → confirmed`. Opposing captain confirms; if no action within 24h it auto-confirms.
  Confirmed → locked immediately (locking triggers ratings).
- **Validation**: sum of player goals per team ≤ team score (football-like); cricket runs/wickets
  reconcile with team totals; values within min/max. Failing checks block submit.
- Staff-entered or staff-confirmed scorecards get `verified_by_staff=True` (higher rating weight).
- **MOTM**: only roster players vote, not for themselves, window closes 24h after submit.
  Tie → higher stat contribution → scorer decides.
- **Peer ratings**: after the match each player may rate up to N others 1–5 (overall + optional
  skill taps). Anonymous to recipients.
- Live scoring (optional, see DECISIONS D6): scorer updates score during the match; followers see it.

## 8. Ratings and track record
- Rating per (player, sport), 1–99, plus shared attributes 1–99.
- Inputs on each locked scorecard: stat performance (sport weights), peer ratings, MOTM, result
  adjusted by opponent average rating, minutes played.
- Weighting: verified scorecards ×1.5; recency decay (recent matches weigh more);
  provisional period (first 10 matches) moves faster.
- Engine is a pure, deterministic module (`apps/ratings/engine.py`) with versioned weights so
  ratings can be recomputed from history.
- Track record: totals per sport and **per ground/turf** (goals, MOTM, wins), form last 5,
  head-to-head, per-turf leaderboards (monthly/all-time).
- Negative record: no-shows, late cancels, cards, upheld conduct reports → reliability and
  fair-play badge. `ConductReport` is reviewed by admin before affecting anything.

## 9. Inventory and store
- `Product` (platform-wide catalogue entry or turf-owned): name, category, images, price,
  `kind=sale|rental`, nutrition (calories, protein, carbs, fat, sugar) where relevant, tags
  (hydration, recovery, pre-match, protein, gear), `perishable`.
- `StockLocation`: either the platform warehouse or a turf. `StockItem(location, product, qty,
  price_override)`. All changes go through `StockMovement` (purchase, sale, counter_sale,
  reservation, release, rental_out, rental_return, adjustment) — qty is derived/consistent.
- Turf staff use a **counter sale (POS)** screen so offline sales decrement stock.
- **Rentals** (bibs, balls, boots, rackets) attach to a match; returned or charged.
- **Store view order**: if the player has an upcoming match → "For your match at X" section
  (platform + that turf's stock) first; then nearby turfs; turf switcher to browse any turf.
- **One order = one stock source.** A cart with items from several sources is split into
  several orders at checkout.
- **Fulfilment matrix**:
  | Source | pickup at turf | deliver to turf (for a match) | deliver to address |
  |---|---|---|---|
  | Platform | — | allowed only if order placed ≥ 16h before match start; delivery charge | allowed anytime; delivery charge |
  | Turf | allowed | n/a (already there) | see DECISIONS D4 |
- Perishables from a turf: pickup only.
- Delivery charge from `DeliveryZone` rules (area → fee, ETA). Cutoff hours configurable.
- Order status: `placed → accepted → packed → out_for_delivery|ready_for_pickup → delivered|picked_up`,
  plus `cancelled`. Stock reserved at placed, committed at delivered/picked_up, released on cancel.
- Payment: cash on delivery / pay at pickup now; online in Phase 10.

## 10. Fitness layer
- Each locked match creates an `ActivityLog(player, sport, minutes, est_calories, match)` using
  `calories = MET × weight_kg × hours` (weight optional on profile; fallback 70 kg, flagged estimated).
- Weekly/monthly activity summary, streaks (weeks with ≥1 match), personal goals.
- Products show macros; filters by tag; **match bundles** (curated product sets, e.g. "Evening
  football kit") addable to a match order in one tap.
- Reminders: hydration 2h before match, recovery tip after, order-cutoff reminder before 16h deadline.

## 11. Notifications
In-app notification centre for every request, approval, invite, booking change, scorecard
action, MOTM result, order update. Email for key events; web push in Phase 9; SMS later.

## 12. Monetization (data must support it)
Per-booking commission or turf subscription, commission on turf sales through the app,
platform store margin, delivery fees. A `LedgerEntry` table records platform/turf amounts per
payment (Phase 10).
