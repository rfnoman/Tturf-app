# Phase 01 — Accounts, Sports Catalogue, Player Profiles

**Goal:** a new user completes onboarding (picks sports, self-assesses) and sees a basic
FIFA-style profile card. Admin manages the sports catalogue.
**Depends on:** 00. **Domain refs:** §1, §2, §3.

## Steps
1. **Sports catalogue** (`apps/sports`)
   - Models: `Sport` (name, slug, icon, `met_value`, is_active), `SportFormat` (sport, name, players_per_side),
     `Attribute` (global: stamina, agility, speed, strength — seeded), `SportAttributeWeight`
     (sport, attribute, weight), `SportSkill` (sport, key, label, weight), `StatDefinition`
     (sport, key, label, type, scope, min, max, order), `SportProposal` (proposed_by, name,
     description, status=pending|approved|merged|rejected, merged_into).
   - Data migration / seed: Football (5v5, 7v7), Futsal, Cricket (box, nets), Badminton (singles, doubles)
     with skills, attribute weights and stat definitions from DOMAIN §7.
   - Admin: full CRUD; action "approve proposal" (creates Sport) and "merge into…".
   - API: `GET /sports` (with formats, skills, stat defs), `POST /sport-proposals` (owners only — for now
     any authenticated user; tighten in Phase 02), admin endpoints for proposals.
2. **Player profile** (`apps/accounts` or new `apps/players`)
   - `PlayerProfile` (1:1 User): display_name, photo (default from Clerk), date_of_birth, gender (optional),
     height_cm, weight_kg (optional, for calories), area, preferred_foot/hand, bio, `discoverable`,
     `reliability_score` (default 100), `onboarding_completed`.
   - `PlayerSport` (player, sport, positions/roles, `is_verified`, `self_assessed` JSON, created_at).
   - `PlayerAttribute` (player, attribute, value 1–99) and `PlayerSkill` (player, sport_skill, value 1–99),
     both with `source = self|computed`.
   - `PlayerSportRating` (player, sport, overall, is_provisional, matches_counted) — overall computed from
     skills + attribute weights by a simple function now; the real engine arrives in Phase 06.
   - Services: `complete_onboarding(user, data)`, `add_player_sport(...)`, `compute_overall(...)`.
   - API: `GET/PATCH /me/profile`, `POST /me/onboarding`, `GET /players/{id}` (public card; respects `discoverable`
     only for search — direct links still work).
3. **Frontend**
   - Onboarding wizard (shown until `onboarding_completed`): basic info → choose sports (multi-select cards)
     → per-sport position + 4–6 quick self-assessment sliders → shared attributes → done.
   - Profile page: FIFA-style card per sport (overall, position, 6 key stats, "Unverified" badge),
     tabs per sport, edit profile.
   - Settings page: discoverable toggle, weight for calorie estimates (with a note why).
4. **Tests:** onboarding validation, overall computation, sport proposal approve/merge, permissions.

## Rules / edge cases
- Self-assessed values are capped (e.g. max 75) so unverified players can't claim 99.
- A player can add/remove sports later; removing a verified sport only hides it (history stays).

## Acceptance checklist
- [ ] Fresh user is forced through onboarding, then lands on their profile card.
- [ ] Profile card shows the right attributes per sport, labelled "Unverified".
- [ ] Admin approves a proposed sport and it appears in the onboarding sport list.
- [ ] Seeded sports have formats, skills and stat definitions visible in the API.

## Prompt for Claude Code
```
Start Phase 01. Read CLAUDE.md, docs/DOMAIN.md §1–3, docs/DECISIONS.md, docs/PROGRESS.md and
docs/phases/01-accounts-sports-profiles.md.

Implement the sports catalogue (with seed data), sport proposals with admin approve/merge,
the player profile models, onboarding service + API, and the frontend onboarding wizard and
FIFA-style profile card as described. Self-assessed ratings must be capped and labelled
unverified. Make the profile card a reusable component — it will be used on the match board,
search results and scorecards later.

Tests first for the services. Regenerate API types, run all checks, update PROGRESS.md.
Present a plan first.
```
