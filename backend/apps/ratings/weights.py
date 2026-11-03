"""Versioned rating weights, one table per sport (DOMAIN §8).

Kept apart from the engine so the arithmetic can stay the same while the numbers are
tuned, and so a rating recomputed later is recomputed with the weights it was *made*
with — ``RatingChange`` stores ``weights_version`` for exactly that reason.

Reading a row: a player who records ``benchmark`` of a stat in one match has had a good
match by that measure. ``weight`` is how much that counts relative to the sport's other
stats, and ``skill`` is the sport skill it moves. Stats nobody can be judged by
(``minutes_played``) are not scored; they set the participation factor instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True)
class StatWeight:
    #: One match's worth of a good return for this stat.
    benchmark: Decimal
    #: Relative importance within the sport. Only positive weights are normalised.
    weight: Decimal
    #: The sport skill this stat moves, if any.
    skill: str | None = None
    #: Points taken straight off the performance score per unit (cards).
    penalty: Decimal = Decimal("0")


@dataclass(frozen=True)
class SportWeights:
    stats: dict[str, StatWeight]
    #: Minutes that count as a full appearance in this sport.
    full_match_minutes: Decimal = Decimal("60")
    #: Skills the engine never moves on stats alone, listed so the omission is deliberate.
    unscored_skills: tuple[str, ...] = field(default_factory=tuple)


#: Bumped whenever any number below changes, so stored explanations stay truthful.
WEIGHTS_VERSION = 1

_FOOTBALL = SportWeights(
    stats={
        "goals": StatWeight(Decimal("1"), Decimal("30"), "finishing"),
        "assists": StatWeight(Decimal("1"), Decimal("20"), "passing"),
        "saves": StatWeight(Decimal("3"), Decimal("20"), "goalkeeping"),
        "clean_sheet": StatWeight(Decimal("1"), Decimal("12"), "defending"),
        "yellow": StatWeight(Decimal("1"), Decimal("0"), None, penalty=Decimal("5")),
        "red": StatWeight(Decimal("1"), Decimal("0"), None, penalty=Decimal("15")),
    },
    full_match_minutes=Decimal("60"),
    unscored_skills=("dribbling", "positioning"),
)

_FUTSAL = SportWeights(
    stats={
        "goals": StatWeight(Decimal("2"), Decimal("30"), "finishing"),
        "assists": StatWeight(Decimal("2"), Decimal("20"), "passing"),
        "saves": StatWeight(Decimal("4"), Decimal("20"), "goalkeeping"),
        "yellow": StatWeight(Decimal("1"), Decimal("0"), None, penalty=Decimal("5")),
        "red": StatWeight(Decimal("1"), Decimal("0"), None, penalty=Decimal("15")),
    },
    full_match_minutes=Decimal("40"),
    unscored_skills=("close_control", "defending"),
)

_CRICKET = SportWeights(
    stats={
        "runs": StatWeight(Decimal("30"), Decimal("30"), "batting"),
        "wickets": StatWeight(Decimal("2"), Decimal("30"), "bowling"),
        "catches": StatWeight(Decimal("1"), Decimal("15"), "fielding"),
    },
    full_match_minutes=Decimal("90"),
    unscored_skills=("wicket_keeping",),
)

_BADMINTON = SportWeights(
    stats={
        "sets_won": StatWeight(Decimal("2"), Decimal("30"), "smash"),
        "points_won": StatWeight(Decimal("40"), Decimal("25"), "net_play"),
        "aces": StatWeight(Decimal("3"), Decimal("20"), "serve"),
        "errors": StatWeight(Decimal("10"), Decimal("0"), None, penalty=Decimal("8")),
    },
    full_match_minutes=Decimal("45"),
    unscored_skills=("footwork", "defence"),
)

SPORT_WEIGHTS: dict[str, SportWeights] = {
    "football": _FOOTBALL,
    "futsal": _FUTSAL,
    "cricket": _CRICKET,
    "badminton": _BADMINTON,
}

#: A sport with no table still gets rated — on result, peers and MOTM alone. That is the
#: whole point of keeping the result and peer components independent of the stats.
GENERIC_WEIGHTS = SportWeights(stats={}, full_match_minutes=Decimal("60"))


def weights_for(sport_slug: str) -> SportWeights:
    return SPORT_WEIGHTS.get(sport_slug, GENERIC_WEIGHTS)
