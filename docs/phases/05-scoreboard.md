# Phase 05 — Scoreboard, MOTM, Peer Ratings

**Goal:** after a match, the scorer enters the score and per-player stats; the other captain
confirms (or disputes); players vote MOTM and rate each other; anyone can view the scorecard.
**Depends on:** 04. **Domain refs:** §7. **Decisions:** D6, D7.

## Steps
1. **Models** (`apps/scoring`)
   - `MatchTeam` (match, side=A|B, name, captain), `MatchTeamPlayer` (team, match_player, position).
   - `Scorecard` (match 1:1, scorer, team_a_score, team_b_score, extra JSON for sport-specific team data
     e.g. cricket overs/wickets, result=A|B|draw, status=draft|submitted|disputed|confirmed|locked,
     submitted_at, confirmed_by, `verified_by_staff`, dispute_reason, resolved_by).
   - `PlayerStat` (scorecard, player, stat_definition, value) — unique per (scorecard, player, stat).
   - `ScorecardEvent` history.
   - `MotmVote` (match, voter, nominee) unique per voter; `Match.motm` FK set when closed.
   - `PeerRating` (match, rater, ratee, overall 1–5, skill_taps JSON) unique per (match, rater, ratee).
2. **Services**
   - `set_teams(match, assignments)` and `auto_balance_teams(match)` (greedy by current sport rating;
     keeps squad mates together optional).
   - `assign_scorer(match, user)` — booker/leader, a captain, or turf staff.
   - `save_draft`, `submit_scorecard` (runs sport validators: goals sum ≤ team score, cricket totals reconcile,
     stat min/max, players must be on roster), `confirm_scorecard` (opposing captain or staff → `verified_by_staff`
     if staff), `dispute_scorecard(reason)`, `resolve_dispute` (staff of that turf or admin, may edit),
     `lock_scorecard` (immediately after confirm; emits a `scorecard_locked` signal Phase 06 will consume).
   - Celery: auto-confirm submitted scorecards after 24h; close MOTM voting 24h after submit; mark attendance
     (roster players with stats = attended).
   - `cast_motm_vote`, `close_motm_voting` (tie-break per DOMAIN §7), `submit_peer_ratings`.
   - Validators are pluggable per sport: `apps/scoring/validators/{football,cricket,racket}.py` registered by sport slug,
     with a generic fallback (min/max only) for new sports.
3. **API**: teams, scorer, scorecard CRUD + transitions, MOTM vote, peer ratings, public
   `GET /matches/{id}/scorecard`, `GET /players/{id}/matches` (recent scorecards).
4. **Frontend**
   - Pre-match: team builder (drag players between A and B, "auto-balance" button, pick captains).
   - Scorecard entry (mobile-first; scorers will use phones at the ground): big +/− steppers for team score and each
     player's stats, form generated from the sport's StatDefinitions. Validation errors inline.
   - Confirm/dispute screen for the opposing captain; dispute resolution for staff/admin.
   - Post-match sheet for each player: MOTM vote + rate teammates/opponents (quick stars).
   - **Public scorecard page**: result header, teams, per-player stats table, MOTM badge, "Verified by turf" badge,
     shareable link with Open Graph image.
5. **Optional step 5b (D6): live scoring** behind `FEATURE_LIVE_SCORING`: scorer updates during the match, followers see
   updates via polling (5s) — server-sent events later.
6. **Tests:** validators per sport, transition matrix, auto-confirm job, MOTM rules (no self-vote, only roster, tie-break),
   peer rating uniqueness, only roster players can be given stats.

## Acceptance checklist
- [ ] Scorer submits 5–3 with goals that add up; the other captain confirms; scorecard locks.
- [ ] Goals that exceed the team score are rejected.
- [ ] Dispute → staff resolves → locked, marked verified.
- [ ] MOTM is decided after 24h (or when all have voted) and shown on the scorecard.
- [ ] Public scorecard link opens without sign-in and looks good when shared on Messenger/WhatsApp.

## Prompt for Claude Code
```
Start Phase 05. Read CLAUDE.md, docs/DOMAIN.md §7, docs/DECISIONS.md (D6, D7),
docs/PROGRESS.md and docs/phases/05-scoreboard.md.

Implement teams and auto-balance, the scorecard state machine with per-sport pluggable
validators driven by StatDefinitions, staff verification, disputes, MOTM voting, peer
ratings, Celery jobs for auto-confirm and vote closing, and emit a scorecard_locked signal
for Phase 06. Build the team builder, a mobile-first scorecard entry screen, the
confirm/dispute flow, the post-match vote/rate sheet and a public shareable scorecard page.

Do not implement live scoring unless I confirm (step 5b). Tests first for validators and
transitions. Run all checks, update PROGRESS.md. Present a plan first.
```
