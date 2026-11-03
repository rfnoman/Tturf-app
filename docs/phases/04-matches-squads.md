# Phase 04 — Matches, Squads, Join Requests, Match Board

**Goal:** every booking becomes a match; players find open matches on the board and request
to join; squads (persistent groups) book together with open/closed rules.
**Depends on:** 03. **Domain refs:** §6. **Decisions:** D1, D2.

## Steps
1. **Models** (`apps/matches`)
   - `Squad` (name, crest/photo, leader, sports, `accepts_public_requests`, area, created_by),
     `SquadMembership` (squad, player, role=leader|member, status=active|left|removed, joined_at),
     `SquadInvite` (squad, player, invited_by, status).
   - `Match` (1:1 booking, sport, format, `capacity`, visibility derived from booking + squad flag, status mirrors
     booking: upcoming|in_progress|finished|cancelled).
   - `MatchPlayer` (match, player, source=booker|squad|request|invite, joined_at, `attended` nullable).
   - `JoinRequest` (match, player, message, status, decided_by, decided_at) — unique pending per (match, player).
   - `MatchInvite` (match, invited_player, invited_by, status=proposed|leader_approved|accepted|declined|cancelled).
   - Link `Booking.squad` FK now.
2. **Services**
   - `create_match_for_booking` (signal or explicit call inside `create_booking`) — booker added; for group
     bookings, booker must be squad leader or member; choose which squad members are in the roster (default all
     active members up to capacity, each gets a notification and can drop out).
   - `request_to_join(match, player)` — only visible matches, not full, not already in, not overlapping another
     match of theirs, before start.
   - `decide_join_request(request, approver, approve, add_to_squad=False)` — approver = booker (individual) or leader.
   - `propose_invite(match, by_member, player)` (closed group → `proposed`), `approve_invite(leader)`,
     `invite_directly(booker|leader, player)`, `respond_invite(player, accept)`.
   - `leave_match`, `remove_player` (approver only), capacity checks everywhere (row lock on match).
   - Squad services: create, invite, join, leave, transfer leadership, remove member.
   - Celery: expire pending requests/invites at match start.
3. **API**
   - `GET /matches/board?sport=&near=&date=&time_from=&time_to=&needed_min=&rating_min=&rating_max=`
   - `GET /matches/{id}` (roster with profile cards, needed, pending requests for approver),
     join request / decide / invite / respond / leave endpoints.
   - Squads CRUD + memberships + invites; `GET /me/squads`.
   - Booking flow from Phase 03 gains: mode=group with squad selection, visibility choice (D2).
4. **Frontend**
   - **Match board**: cards "Mirpur Turf · Ground 2 · Fri 9:00 PM · 7v7 · Need 3 · Avg rating 68", filters,
     list/map toggle, "Request to join" with optional message.
   - Match page: roster (profile cards), slots left, approver's pending requests panel (approve/decline,
     "also add to squad" checkbox), invite player (search squad members/people they've played with —
     full player search arrives in Phase 06), leave match.
   - Squads: create squad, squad page (members, upcoming matches, open/closed toggle for leader),
     invite members.
   - Booking flow: individual vs group + public/private + squad picker.
5. **Tests:** every visibility combination × who can see/request/invite; capacity race (two approvals for last
   spot); overlapping-match prevention; closed-group invite chain; expiry at start.

## Acceptance checklist
- [ ] Player A books publicly, needs 9; Player B finds it on the board, requests; A approves; B is on the roster.
- [ ] Open squad match appears on the board; leader approves requests.
- [ ] Closed squad match is invisible on the board; member proposes a player; leader approves; player accepts.
- [ ] A full match blocks new requests; the last spot can't be given twice.

## Prompt for Claude Code
```
Start Phase 04. Read CLAUDE.md, docs/DOMAIN.md §6, docs/DECISIONS.md (D1, D2),
docs/PROGRESS.md and docs/phases/04-matches-squads.md.

Implement squads, matches (one per booking), rosters, join requests, invites (including the
closed-group propose → leader approve → player accept chain), capacity checks with row
locks, expiry jobs, and the match board API with filters. Build the match board UI, match
page with approver panel, squad pages, and extend the booking flow with group mode and
visibility.

Write a test matrix covering every visibility mode × role (outsider, member, leader, booker)
for see/request/invite/approve before implementing. Run all checks, update PROGRESS.md.
Present a plan first.
```
