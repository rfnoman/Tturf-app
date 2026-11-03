# Phase 06 — Ratings Engine, Track Record, Player Discovery

**Goal:** ratings update automatically after each locked scorecard; profiles show a real track
record (good and bad); squads can search for and invite players from outside their group.
**Depends on:** 05. **Domain refs:** §3, §8, §6 (invites). **Decisions:** D1, D7.

## Steps
1. **Rating engine** (`apps/ratings/engine.py`, pure Python, no ORM inside)
   - Input: a `MatchPerformance` dataclass per player (sport, stats dict, minutes, result, team avg rating,
     opponent avg rating, MOTM flag, peer ratings, verified flag, player's current ratings and match count).
   - Output: new sport overall, new skill values, new shared attribute values, and an explanation breakdown
     (stored so the profile can show "why my rating changed").
   - Weights per sport in a versioned config (`RATING_WEIGHTS_VERSION`), e.g. stat → skill mapping
     (goals → finishing, saves → goalkeeping, wickets → bowling), minutes → stamina.
   - Rules: verified ×1.5; provisional K-factor for first 10 matches; clamp changes per match (±3 overall);
     recency handled by the incremental update (EMA style).
   - Deterministic → `recompute_all(player, sport)` replays history; management command `recompute_ratings`.
2. **Integration**
   - Receiver for `scorecard_locked`: build performances, run engine, write `PlayerSportRating`, `PlayerSkill`,
     `PlayerAttribute` (`source=computed`), `RatingChange` (player, sport, match, before, after, breakdown).
   - Sport unlock: mark `PlayerSport.is_verified=True` or create it.
   - Track record aggregates: `PlayerSportStats` (totals) and `PlayerGroundStats` (player, turf, ground, sport:
     matches, wins, MOTM, key stat totals) updated incrementally; form = last 5 results.
3. **Conduct & fair play**
   - `ConductReport` (match, reporter, reported, reason=abusive|left_early|no_show|unsafe_play|other, details,
     status=open|upheld|dismissed, reviewed_by). Only roster players can report, once per match per person.
   - Fair-play score from cards, upheld reports, no-shows, late cancels; badge thresholds (Good / Warning / Poor).
   - Admin review queue.
4. **Leaderboards**: per turf and per sport — top scorers, most MOTM, highest rated, most reliable; monthly and
   all-time; computed by a Celery task nightly into a `LeaderboardEntry` table.
5. **Player discovery**
   - `available_to_play` windows: `Availability` (player, sport, start, end, area, note).
   - `GET /players/search?sport=&position=&rating_min=&rating_max=&area=&near=&reliability_min=&played_at_turf=&available_on=`
     respecting `discoverable`; ranking by relevance (area/distance, rating fit, reliability).
   - From search or a profile: "Invite to match" (pick one of the inviter's upcoming matches) → uses the Phase 04
     invite chain (D1); "Invite to squad".
6. **Frontend**
   - Profile upgrade: FIFA card with real ratings, "Verified" once unlocked, rating history chart, "why it changed"
     breakdown, track record tab (totals, per-ground highlights e.g. "3× MOTM at Mirpur Turf"), form guide,
     fair-play & reliability badges, recent scorecards.
   - Player search page with filters and card grid; "I'm available" quick action on home.
   - Turf page: leaderboards tab.
   - Admin: conduct report queue.
7. **Tests:** engine unit tests with fixed scenarios (golden values), clamp and provisional behaviour, recompute
   equals incremental result, aggregates, search filters + discoverable, conduct report permissions.

## Acceptance checklist
- [ ] After a locked match, each player's rating changes and the breakdown explains why.
- [ ] Recomputing from history gives the same ratings.
- [ ] Profile shows per-ground highlights and form; a no-show appears in reliability.
- [ ] A squad member finds a "free tonight" striker in Mirpur and invites them through the approval chain.
- [ ] Turf leaderboard shows the top scorers this month.

## Prompt for Claude Code
```
Start Phase 06. Read CLAUDE.md, docs/DOMAIN.md §3, §6 and §8, docs/DECISIONS.md,
docs/PROGRESS.md and docs/phases/06-ratings-discovery.md.

Build the pure, deterministic, versioned rating engine with golden-value unit tests first,
then hook it to the scorecard_locked signal with RatingChange history, sport unlocking,
track record aggregates (overall and per ground), conduct reports with admin review,
fair-play badges, nightly leaderboards, availability windows and player search with invite
to match/squad through the existing invite chain. Upgrade the profile UI with rating
history, change breakdown and track record; add the player search page and turf leaderboards.

Propose the initial weights per sport in a table for me to review before coding them.
Run all checks, update PROGRESS.md. Present a plan first.
```
