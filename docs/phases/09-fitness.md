# Phase 09 — Fitness Layer, Reminders, Real-time Notifications

**Goal:** the app feels built for fitness-minded players: every match counts as a workout,
products match training needs, and timely nudges help players prepare and recover.
**Depends on:** 05, 08. **Domain refs:** §10, §11.

## Steps
1. **Models** (`apps/fitness`)
   - `ActivityLog` (player, sport, match nullable, minutes, est_calories, `is_estimate`, source=match|manual, date).
   - `FitnessGoal` (player, type=matches_per_week|minutes_per_week|calories_per_week, target, active).
   - `Streak` stored or computed (weeks with ≥1 match; current + best).
   - `Bundle` (name, description, sport, occasion=pre_match|during|recovery, items (product + qty), source scope,
     image, active) — curated by admin (platform) or turf owner (turf).
   - `ReminderPreference` (player: hydration, recovery, cutoff, match_day on/off; quiet hours).
2. **Services**
   - On `scorecard_locked` (and for completed matches without a scorecard, using booking duration):
     create ActivityLog with `calories = MET × weight_kg × hours` (fallback 70 kg → `is_estimate=True`).
   - Weekly summary (minutes, matches, calories, sports mix), goal progress, streak update.
   - `add_bundle_to_cart(player, bundle, source, match)`.
   - Reminder jobs (Celery beat): match-day morning summary, hydration 2h before, order cutoff (from Phase 08, now
     respecting preferences), post-match recovery tip with bundle suggestion, weekly recap.
3. **Notifications upgrade**
   - Web push (VAPID, service worker) with per-type preferences; keep in-app + email.
   - Real-time in-app updates: server-sent events or Django Channels for notifications, join requests and
     live scoring (if enabled). Pick one, record in DECISIONS.md.
4. **Frontend**
   - **Home dashboard** for players: next match card, "this week" ring (minutes/goal), streak, recent ratings change,
     suggested bundle for the next match, open matches near you.
   - Activity page: weekly/monthly charts, history list, add manual activity (e.g. gym session), goals.
   - Store: bundle cards, "fitness filters" (high protein, low sugar, hydration), nutrition comparison on product pages.
   - Settings: reminder preferences, push opt-in.
5. **Tests:** calorie calc and fallback flag, streak edges (week boundaries in Asia/Dhaka), goal progress, reminder
   scheduling respects preferences and quiet hours, bundle to cart with partial stock.

## Acceptance checklist
- [ ] After a 60-min football match, the player's activity shows minutes and estimated calories.
- [ ] Streak and weekly goal update correctly across a Dhaka week boundary.
- [ ] A hydration push arrives 2h before the match (when enabled) and not during quiet hours.
- [ ] "Evening football kit" bundle adds all items to the cart in one tap.

## Prompt for Claude Code
```
Start Phase 09. Read CLAUDE.md, docs/DOMAIN.md §10–11, docs/DECISIONS.md, docs/PROGRESS.md
and docs/phases/09-fitness.md.

Implement activity logs from matches with MET-based calorie estimates, goals, streaks,
curated bundles with one-tap add-to-cart, reminder preferences and Celery reminder jobs,
web push notifications, and a real-time channel for in-app notifications (propose SSE vs
Channels with trade-offs before choosing). Build the player home dashboard, activity page,
bundle and fitness filters in the store, and reminder settings.

Tests first for calorie, streak and reminder scheduling logic (Asia/Dhaka week boundaries).
Run all checks, update PROGRESS.md and DECISIONS.md. Present a plan first.
```
