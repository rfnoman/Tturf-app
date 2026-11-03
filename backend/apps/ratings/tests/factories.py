"""A locked scorecard, which is where every rating in this app comes from."""

from __future__ import annotations

from decimal import Decimal

from apps.players.services import (
    add_player_sport,
    get_or_create_profile,
    set_player_attributes,
)
from apps.scoring.models import TeamSide
from apps.scoring.services import (
    confirm_scorecard,
    lock_scorecard,
    save_draft,
    submit_scorecard,
)
from apps.scoring.tests.factories import ready_to_score
from apps.sports.models import Sport, SportSkill, StatDefinition


def onboard_everyone(match, *, sport: str = "football", skill: int = 50):
    """Give every player on the roster a full profile, so there is something to move.

    The skills matter: the engine deliberately refuses to invent a skill row a player
    does not have, so a profile onboarded with none would never show a skill change.
    """
    skills = dict.fromkeys(
        SportSkill.objects.filter(sport__slug=sport).values_list("key", flat=True), skill
    )
    sport_row = Sport.objects.get(slug=sport)

    for entry in match.players.select_related("player"):
        # Joining a match already creates a bare profile, so this fills one in rather
        # than onboarding from scratch.
        profile = get_or_create_profile(entry.player)
        set_player_attributes(
            profile=profile,
            values={"stamina": skill, "agility": skill, "speed": skill, "strength": skill},
        )
        add_player_sport(profile=profile, sport=sport_row, skills=skills)


def locked_match(
    *,
    players: int = 4,
    sport: str = "football",
    fmt: str = "5v5",
    scores: tuple[int, int] = (3, 1),
    stats: dict | None = None,
    verified: bool = False,
    motm=None,
):
    """A finished match, scored, confirmed and locked.

    ``stats`` is ``{side: {stat key: value}}`` applied to the *first* player on each
    side, which is enough to say "this player scored and that one did not" without
    every test having to know the roster order.
    """
    match, teams, scorecard = ready_to_score(players=players, sport=sport, fmt=fmt)
    onboard_everyone(match, sport=sport)

    per_player: dict = {}
    for side, values in (stats or {}).items():
        first = teams[side].players.first()
        if first is None:
            continue
        per_player[str(first.match_player.player_id)] = {
            key: Decimal(str(value)) for key, value in values.items()
        }

    scorer = teams[TeamSide.A].captain
    save_draft(
        scorecard=scorecard,
        actor=scorer,
        team_a_score=scores[0],
        team_b_score=scores[1],
        stats=per_player,
    )
    submit_scorecard(scorecard=scorecard, actor=scorer)

    if motm is not None:
        scorecard.motm = motm
        scorecard.save(update_fields=["motm"])
    if verified:
        scorecard.verified_by_staff = True
        scorecard.save(update_fields=["verified_by_staff"])

    confirm_scorecard(scorecard=scorecard, actor=teams[TeamSide.B].captain)
    scorecard.refresh_from_db()
    if not scorecard.is_locked:
        lock_scorecard(scorecard=scorecard, actor=None)
        scorecard.refresh_from_db()

    return match, teams, scorecard


def stat_keys(sport_slug: str) -> set[str]:
    return set(
        StatDefinition.objects.filter(
            sport__slug=sport_slug, scope=StatDefinition.Scope.PLAYER
        ).values_list("key", flat=True)
    )
