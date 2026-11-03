# Phase 10 — Online Payments, Advances, Ledger, Payouts

**Goal:** players can pay online (cards and mobile wallets); turfs can require an advance to
cut no-shows; refunds follow the cancellation policy; the platform tracks commissions and
owner payouts.
**Depends on:** 03, 08. **Domain refs:** §5, §12. **Decisions:** D8.

## Steps
1. **Provider abstraction** (`apps/payments/providers/`)
   - `PaymentProvider` interface: `init_payment(payment) → redirect_url`, `verify(callback_data)`,
     `handle_ipn(request)`, `refund(payment, amount)`. Implementations: `CashProvider` (existing),
     `SSLCommerzProvider` (sandbox first). bKash direct later behind the same interface.
   - Check current SSLCommerz API docs; validate every callback server-side with their validation API — never trust
     the redirect alone. Idempotent IPN handling.
2. **Models**: extend `Payment` (provider, provider_txn_id, gateway_status, raw_response, kind=full|advance|balance),
   `Refund` (payment, amount, reason, status), `LedgerEntry` (payment/refund, account=platform|turf:<id>|delivery,
   amount ±, type=booking_fee|commission|sale|delivery_fee|refund|payout), `Payout` (turf, period, amount, status,
   reference), `CommissionPlan` (turf or default: booking %, sales %, or subscription).
3. **Services**
   - Booking: turf setting `advance_percent` (default from D8). Booking with advance stays `reserved` until advance is paid
     (then auto-confirms regardless of D3), balance paid at turf in cash or online.
   - Orders: online payment option at checkout.
   - Refund calculation from the cancellation policy (full refund before free window; advance forfeited after),
     owner-initiated cancellations always full refund.
   - Ledger posting on each successful payment/refund (double-entry style: entries for one event sum to zero).
   - Payout statement per turf per period; admin marks payout paid (manual bank/bKash transfer for now).
4. **Frontend**: payment step in booking and checkout (choose cash / pay online / pay advance), redirect + result pages,
   payment history for players, owner finance page (earnings, commissions, payouts, downloadable statement CSV),
   admin finance dashboard and refund management.
5. **Tests:** provider mocked end-to-end (success, fail, cancel, duplicate IPN, amount mismatch), refund policy table,
   ledger always balances, advance flow transitions.

## Acceptance checklist
- [ ] Sandbox card payment for an advance confirms the booking; balance marked paid in cash at the turf.
- [ ] Duplicate or forged callbacks don't double-confirm or mark paid.
- [ ] Late cancellation forfeits the advance; owner cancellation refunds in full.
- [ ] Owner finance page matches the ledger; payout statement downloads.

## Prompt for Claude Code
```
Start Phase 10. Read CLAUDE.md, docs/DOMAIN.md §5 and §12, docs/DECISIONS.md (D8),
docs/PROGRESS.md and docs/phases/10-payments.md.

Implement a payment provider abstraction with SSLCommerz (sandbox) using its current official
docs, server-side validation and idempotent IPN handling; advance payments for bookings,
online payment for orders, policy-based refunds, a balanced ledger, commission plans and payout
statements. Build the payment steps, result pages, player payment history, owner finance page
and admin finance/refunds.

Tests first for callback security cases and the refund policy table. Never log card data or
secrets. Run all checks, update PROGRESS.md. Present a plan first, and list the SSLCommerz
credentials I need to obtain.
```
