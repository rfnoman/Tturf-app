# Development Plan

Twelve phases. Each one ends with something that runs end to end and is tested, so the app
is usable (and demo-able) after every phase. Each phase file in `docs/phases/` contains
scope, business rules, acceptance criteria, and a **prompt to paste into Claude Code**.

| # | Phase | Result you can demo | Depends on |
|---|---|---|---|
| 00 | [Foundation](phases/00-foundation.md) | Sign in with Clerk; frontend calls Django `/me` | — |
| 01 | [Accounts, sports, profiles](phases/01-accounts-sports-profiles.md) | Onboarding: pick sports, self-assess, see basic profile card | 00 |
| 02 | [Turfs & grounds](phases/02-turfs-grounds.md) | Owner registers turf + grounds + prices; admin approves; players find turfs near them | 01 |
| 03 | [Bookings & cash payment](phases/03-bookings-cash.md) | Player books a slot; owner/staff confirm, mark paid, no-show; notifications | 02 |
| 04 | [Matches, squads, joining](phases/04-matches-squads.md) | Match board; join requests; squads; open/closed group flows | 03 |
| 05 | [Scoreboard](phases/05-scoreboard.md) | Teams, scorecard entry, confirm/dispute, MOTM votes, peer ratings | 04 |
| 06 | [Ratings, track record, discovery](phases/06-ratings-discovery.md) | FIFA-style ratings update after matches; player search; invite outsiders; leaderboards | 05 |
| 07 | [Inventory & counter POS](phases/07-inventory-pos.md) | Turf stock, counter sales, rentals; platform warehouse stock | 02 |
| 08 | [Store, orders, delivery](phases/08-store-delivery.md) | Match-aware store, split carts, pickup/turf/home delivery, 16h rule, rider flow | 07, 04 |
| 09 | [Fitness layer & notifications+](phases/09-fitness.md) | Activity log, calories, streaks, bundles, reminders, web push | 05, 08 |
| 10 | [Online payments & ledger](phases/10-payments.md) | SSLCommerz checkout, advances, refunds, commissions, owner payouts | 03, 08 |
| 11 | [Hardening, Bangla, launch](phases/11-launch.md) | Full Bangla, PWA, security, monitoring, production deploy | all |

Phase 07 only needs 02, so it can run in parallel with 03–06 if you want two tracks.

## How to run a phase in Claude Code
1. Open the `turf-app` folder in Claude Code. `CLAUDE.md` is loaded automatically.
2. Create a branch: `git checkout -b phase-03-bookings`.
3. Switch to **plan mode** (Shift+Tab) and paste the phase's prompt. Review the plan it
   proposes, adjust, then let it implement.
4. When it reports done, check the phase's **Acceptance checklist** yourself (run the app).
5. Make sure `docs/PROGRESS.md` was updated, then merge the branch.
6. If you changed your mind on a rule, edit `docs/DOMAIN.md` / `docs/DECISIONS.md` *first*,
   then ask Claude Code to apply the change.

Tips:
- Big phases are split into numbered steps. If context gets long, run `/clear` and continue
  with: "Continue Phase NN from step X. Read PROGRESS.md first."
- Keep each phase's work in its own branch and PR; it makes rollback easy.
- Ask Claude Code to write tests before the service code for the state machines
  (bookings, join requests, scorecards, orders) — these are where bugs hide.

## Definition of done (every phase)
- Migrations created and applied cleanly on a fresh DB.
- `uv run pytest` green; service functions and state transitions covered.
- `npm run lint && npm run typecheck` green; API types regenerated.
- Playwright happy-path test(s) for the phase pass.
- Django admin registered for new models (useful for support).
- Seed command (`manage.py seed_demo`) extended with demo data for the new features.
- New strings present in `en.json` and `bn.json`.
- `docs/PROGRESS.md` updated.
