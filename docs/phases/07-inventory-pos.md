# Phase 07 — Inventory, Rentals, Counter POS

**Goal:** turf owners and the platform manage stock in one consistent system; staff sell at
the counter so stock stays accurate; gear can be rented for a match.
**Depends on:** 02 (can run in parallel with 03–06). **Domain refs:** §9 (inventory part).

## Steps
1. **Models** (`apps/inventory`)
   - `ProductCategory` (drinks, food, supplements, gear, apparel, accessories, rental gear).
   - `Product` (owner_type=platform|turf, turf nullable, name, slug, description, images, category, base_price,
     `kind=sale|rental`, rental_price_per_match, deposit, `perishable`, nutrition fields (serving_size, calories,
     protein_g, carbs_g, fat_g, sugar_g, caffeine_mg), tags (hydration, recovery, pre_match, protein, low_sugar,
     vegan, gear), sport relevance M2M, is_active, barcode/SKU).
   - `StockLocation` (type=warehouse|turf, turf nullable, name, address/location).
   - `StockItem` (location, product, `on_hand`, `reserved`, price_override, low_stock_threshold) —
     `available = on_hand − reserved`.
   - `StockMovement` (stock_item, type, qty_delta, reserved_delta, reference (order/sale/rental), actor, note).
     **Only services create movements and update StockItem in the same transaction with `select_for_update`.**
   - `CounterSale` (turf, staff, items, total, payment_method=cash, customer (optional player/phone), match (optional)).
   - `Rental` (match or booking, player, product, qty, status=reserved|out|returned|lost, deposit, charges).
2. **Services**: `receive_stock`, `adjust_stock(reason)`, `reserve`, `release`, `commit_sale`,
   `record_counter_sale` (decrements on_hand), `rent_out`, `return_rental`, `mark_rental_lost`,
   low-stock notification to owner/staff.
3. **API**
   - Owner/staff: product CRUD for their turf, stock list with available/reserved, receive/adjust, movement history,
     counter sale (product search by name/barcode), rentals for today's matches.
   - Platform admin: warehouse products/stock.
   - Public read: `GET /turfs/{id}/products` and `GET /store/platform/products` (used by Phase 08).
4. **Frontend**
   - Owner inventory: product list with stock badges, add/edit product (nutrition section shown for food/drink),
     receive stock, adjust with reason, movement log.
   - **Counter POS** (tablet/phone friendly): product grid by category, cart, quick quantity, total in BDT,
     "cash received" → change due, optional attach to a booking/match.
   - Rentals board: today's matches with rented items, mark out/returned.
   - Admin: warehouse inventory screens.
5. **Tests:** concurrency on reserve (no negative available), movement ledger always reconciles with StockItem,
   rental lifecycle, permissions per turf.

## Acceptance checklist
- [ ] Cashier sells 3 waters at the counter → stock drops by 3, movement logged.
- [ ] Reserving more than available fails even with parallel requests.
- [ ] Bibs rented for a match are tracked out and returned.
- [ ] Products show nutrition facts; low-stock alerts reach the owner.

## Prompt for Claude Code
```
Start Phase 07. Read CLAUDE.md, docs/DOMAIN.md §9, docs/DECISIONS.md, docs/PROGRESS.md and
docs/phases/07-inventory-pos.md.

Implement the product catalogue (platform and turf-owned, with nutrition and fitness tags),
stock locations, stock items with on_hand/reserved, an append-only StockMovement ledger
updated only through services with row locks, counter sales, rentals and low-stock alerts.
Build owner inventory screens, a fast tablet-friendly counter POS, a rentals board and admin
warehouse screens. Expose public product endpoints Phase 08 will use.

Tests first for the ledger invariant and concurrent reservations. Seed realistic BD products
(water, electrolyte drinks, bananas, protein bars, bibs, footballs) with BDT prices.
Run all checks, update PROGRESS.md. Present a plan first.
```
