# Phase 08 — Store, Orders, Delivery

**Goal:** players shop from the platform and any turf; the store puts their next match first;
they choose pickup, delivery to the turf (16h rule) or delivery to an address; riders deliver.
**Depends on:** 07, 04. **Domain refs:** §9. **Decisions:** D4, D5.

## Steps
1. **Models** (`apps/store`)
   - `DeliveryZone` (name, areas list or polygon (PostGIS), fee, eta_hours, `turf_delivery_cutoff_hours` override, active).
   - `Address` (player, label, line, area, location point, phone).
   - `Cart` (player) and `CartItem` (stock_item, qty) — items from different sources allowed in the cart.
   - `Order` (player, source_location, fulfilment=pickup_at_turf|deliver_to_turf|deliver_to_address,
     match (for deliver_to_turf / optional for pickup), address, subtotal, delivery_fee, total,
     payment_method=cod|pay_at_pickup, status, rider, scheduled_for, notes),
     `OrderItem` (product snapshot: name, unit_price, qty, nutrition snapshot), `OrderEvent`.
   - `RiderProfile` (user, zones, active).
2. **Services**
   - `get_fulfilment_options(player, source, match=None, address=None)` → allowed options with fee, ETA and
     reasons for disabled ones. Rules from DOMAIN §9 matrix:
     - platform → turf only if `now ≤ match.start − cutoff` (D5) and the player is on that match roster;
     - platform → address any time, fee by zone (reject if address outside all zones);
     - turf stock → pickup only (D4); perishables always pickup.
   - `checkout(cart, choices_per_source)` — splits into one order per source, reserves stock (Phase 07 services),
     snapshots prices, all-or-nothing transaction.
   - Transitions: `accept_order` (source staff/admin), `pack`, `assign_rider`, `mark_out_for_delivery`, `mark_ready_for_pickup`,
     `mark_delivered` / `mark_picked_up` (commit stock, record cash Payment), `cancel_order` (release stock;
     player can cancel until packed).
   - Celery: remind players before the cutoff for their upcoming match ("Order by 5 AM to get it at the turf");
     flag deliver-to-turf orders not out for delivery N hours before match.
3. **API**: store home (personalised sections), products by source with filters (category, tag, sport, max calories,
   min protein), cart CRUD, fulfilment options, checkout, my orders, order tracking; staff order queue per turf;
   admin order queue for platform; rider: my deliveries + status updates.
4. **Frontend**
   - **Store home**: if upcoming match → hero "For your match at Mirpur Turf, Fri 9 PM" with platform + that turf's
     products and a cutoff countdown; then "Nearby turfs"; source switcher (Platform / any turf with search); filters
     and fitness tags; product page with nutrition facts.
   - Cart grouped by source, with fulfilment choice per group (disabled options explain why), address picker/map,
     fee and total, place order.
   - Order tracking page with status timeline.
   - Turf staff: incoming orders (pickup) on the dashboard next to bookings; platform admin: order queue,
     assign rider; rider: mobile list of deliveries with call/map links and status buttons.
   - Match page: "Items for this match" (orders delivered to the turf for this match).
5. **Tests:** fulfilment matrix (each cell + cutoff boundaries at exactly 16h), cart split, stock reservation/release on
   cancel, zone fee lookup, perishable rule, permissions (rider sees only assigned orders).

## Acceptance checklist
- [ ] Player with a match tomorrow 9 PM sees "For your match" first; at 4:59 AM the deliver-to-turf option works,
      at 5:01 AM it is disabled with an explanation.
- [ ] Cart with platform + turf items checks out into two orders with correct options.
- [ ] Home delivery charges the zone fee; outside all zones is refused politely.
- [ ] Rider marks delivered → stock committed, cash payment recorded.

## Prompt for Claude Code
```
Start Phase 08. Read CLAUDE.md, docs/DOMAIN.md §9, docs/DECISIONS.md (D4, D5),
docs/PROGRESS.md and docs/phases/08-store-delivery.md.

Implement delivery zones, addresses, carts, the fulfilment-options service encoding the
DOMAIN §9 matrix and 16h cutoff (configurable), checkout that splits the cart into one order
per stock source with stock reservation, the order state machine with rider assignment,
cash on delivery/pickup payments, and cutoff reminder jobs. Build the match-aware store home,
cart with per-source fulfilment choice, order tracking, staff/admin order queues and a mobile
rider view.

Tests first for every cell of the fulfilment matrix including exact cutoff boundaries.
Run all checks, update PROGRESS.md. Present a plan first.
```
