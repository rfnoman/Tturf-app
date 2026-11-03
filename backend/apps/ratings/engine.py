"""The rating engine: pure, deterministic, and free of the ORM (DOMAIN §8).

One match in, one set of new numbers out, plus the breakdown that explains them. Nothing
here reads the database — which is what makes `recompute_all` able to replay a player's
whole history and arrive at exactly the ratings the incremental updates produced.

How a match becomes a number:

1. **Stats** → a 0–100 score. Each scored stat is measured against the sport's benchmark
   and capped at 1.5× it, so one lopsided scoreline cannot mint a 99. A player with no
   notable stats scores `STAT_BASELINE`, not zero: a defender who kept it quiet has not
   had a bad match, and the result and peer components are what judge them.
2. **Result** → win, draw or loss, shifted by how strong the opposition was.
3. **Peers** → the 1–5 ratings their teammates and opponents gave them.

Those combine into one performance score, the player's rating moves a fraction of the
way towards it, and that fraction is clamped. Provisional players (their first
`RATING_PROVISIONAL_MATCHES` matches) move faster, and a card a turf verified counts for
more (`RATING_VERIFIED_SCORECARD_WEIGHT`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from .weights import WEIGHTS_VERSION, SportWeights, weights_for

RATING_MIN = 1
RATING_MAX = 99

#: What a player scores on stats alone for simply playing.
STAT_BASELINE = Decimal("40")
#: How far above the benchmark a single stat can count.
STAT_CAP = Decimal("1.5")

#: How the three components make up one performance score. Renormalised when a component
#: is missing — a match nobody rated is judged on stats and result, not marked down.
COMPONENT_WEIGHTS = {
    "stats": Decimal("0.45"),
    "result": Decimal("0.35"),
    "peers": Decimal("0.20"),
}

RESULT_SCORE = {"win": Decimal("85"), "draw": Decimal("60"), "loss": Decimal("40")}
#: Beating stronger opponents is worth more; the swing is deliberately small.
OPPONENT_SWING_CAP = Decimal("10")
MOTM_BONUS = Decimal("6")


@dataclass(frozen=True)
class MatchPerformance:
    """Everything the engine needs about one player in one locked match."""

    sport_slug: str
    #: ``{stat key: value}`` as recorded on the scorecard.
    stats: dict[str, Decimal] = field(default_factory=dict)
    result: str = "draw"
    minutes: Decimal | None = None
    team_average: int | None = None
    opponent_average: int | None = None
    is_motm: bool = False
    #: Mean of the 1–5 ratings this player received, and how many there were.
    peer_average: Decimal | None = None
    peer_count: int = 0
    verified: bool = False

    #: Where the player stands going in.
    current_overall: int = 50
    current_skills: dict[str, int] = field(default_factory=dict)
    current_attributes: dict[str, int] = field(default_factory=dict)
    matches_counted: int = 0


@dataclass(frozen=True)
class RatingOutcome:
    overall: int
    skills: dict[str, int]
    attributes: dict[str, int]
    #: Why it changed, stored on `RatingChange` and shown on the profile.
    breakdown: dict
    weights_version: int = WEIGHTS_VERSION


def _decimal(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _clamp(value: Decimal, low: Decimal, high: Decimal) -> Decimal:
    return max(low, min(high, value))


def _round(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _rating(value: Decimal) -> int:
    return _round(_clamp(value, Decimal(RATING_MIN), Decimal(RATING_MAX)))


def _participation(performance: MatchPerformance, weights: SportWeights) -> Decimal:
    """How much of the match they were on for, 0.25–1.

    Unrecorded minutes mean a full appearance: most scorers will not fill it in, and
    assuming the worst would punish every player at every turf that does not track it.
    """
    if performance.minutes is None or weights.full_match_minutes <= 0:
        return Decimal("1")
    ratio = _decimal(performance.minutes) / weights.full_match_minutes
    return _clamp(ratio, Decimal("0.25"), Decimal("1"))


def _stat_ratio(performance: MatchPerformance, weights: SportWeights) -> tuple[Decimal, Decimal]:
    """Weighted achievement 0–1 across the sport's scored stats, and the card penalty."""
    total_weight = sum(
        (stat.weight for stat in weights.stats.values() if stat.weight > 0), Decimal("0")
    )
    earned = Decimal("0")
    penalty = Decimal("0")

    for key, stat in weights.stats.items():
        value = _decimal(performance.stats.get(key, 0))
        if stat.penalty > 0:
            penalty += value * stat.penalty
        if stat.weight <= 0 or stat.benchmark <= 0:
            continue
        earned += _clamp(value / stat.benchmark, Decimal("0"), STAT_CAP) * stat.weight

    if total_weight <= 0:
        return Decimal("0"), penalty
    return earned / (total_weight * STAT_CAP), penalty


def _result_component(performance: MatchPerformance) -> Decimal:
    base = RESULT_SCORE.get(performance.result, RESULT_SCORE["draw"])
    if performance.team_average is None or performance.opponent_average is None:
        return base
    gap = _decimal(performance.opponent_average - performance.team_average)
    return _clamp(
        base + _clamp(gap, -OPPONENT_SWING_CAP, OPPONENT_SWING_CAP), Decimal("0"), Decimal("100")
    )


def _peer_component(performance: MatchPerformance) -> Decimal | None:
    if not performance.peer_count or performance.peer_average is None:
        return None
    # 1–5 onto 0–100: a straight 3 is a 50, which is what "average" should mean.
    return _clamp((_decimal(performance.peer_average) - 1) / 4 * 100, Decimal("0"), Decimal("100"))


def match_performance_score(performance: MatchPerformance) -> dict:
    """The 0–100 verdict on one match, with each component kept for the explanation."""
    weights = weights_for(performance.sport_slug)

    ratio, penalty = _stat_ratio(performance, weights)
    participation = _participation(performance, weights)
    # Stats are scaled by time on the pitch; a substitute's 20 minutes are not a quiet
    # 90. The baseline is not scaled — they still played.
    stats_component = _clamp(
        STAT_BASELINE + (Decimal("100") - STAT_BASELINE) * ratio * participation - penalty,
        Decimal("0"),
        Decimal("100"),
    )
    result_component = _result_component(performance)
    peers_component = _peer_component(performance)

    components = {"stats": stats_component, "result": result_component}
    if peers_component is not None:
        components["peers"] = peers_component

    total_weight = sum(COMPONENT_WEIGHTS[name] for name in components)
    score = (
        sum(value * COMPONENT_WEIGHTS[name] for name, value in components.items()) / total_weight
    )

    if performance.is_motm:
        score += MOTM_BONUS

    return {
        "score": _clamp(score, Decimal("0"), Decimal("100")),
        "components": dict(components),
        "participation": participation,
        "stat_ratio": ratio,
        "card_penalty": penalty,
        "motm_bonus": MOTM_BONUS if performance.is_motm else Decimal("0"),
    }


# ---------------------------------------------------------------------------
# Moving the numbers
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Movement:
    """How fast a value may move, and how far in one match."""

    provisional_rate: Decimal
    settled_rate: Decimal
    provisional_clamp: Decimal
    settled_clamp: Decimal

    def rate(self, *, provisional: bool) -> Decimal:
        return self.provisional_rate if provisional else self.settled_rate

    def clamp(self, *, provisional: bool) -> Decimal:
        return self.provisional_clamp if provisional else self.settled_clamp


#: DOMAIN §8: "provisional period (first 10 matches) moves faster", and the phase file
#: asks for a ±3 clamp per match. Provisional players get a wider clamp as well as a
#: bigger step, or the faster rate would be throttled by the clamp and mean nothing.
OVERALL_MOVEMENT = Movement(
    provisional_rate=Decimal("0.30"),
    settled_rate=Decimal("0.12"),
    provisional_clamp=Decimal("6"),
    settled_clamp=Decimal("3"),
)
SKILL_MOVEMENT = Movement(
    provisional_rate=Decimal("0.25"),
    settled_rate=Decimal("0.10"),
    provisional_clamp=Decimal("5"),
    settled_clamp=Decimal("2"),
)
ATTRIBUTE_MOVEMENT = Movement(
    provisional_rate=Decimal("0.12"),
    settled_rate=Decimal("0.06"),
    provisional_clamp=Decimal("3"),
    settled_clamp=Decimal("1"),
)


def _move(
    current: int,
    target: Decimal,
    movement: Movement,
    *,
    provisional: bool,
    multiplier: Decimal,
) -> tuple[int, Decimal]:
    """Step `current` towards `target`, scaled and clamped. Returns the value and delta."""
    raw = (target - Decimal(current)) * movement.rate(provisional=provisional) * multiplier
    limit = movement.clamp(provisional=provisional)
    delta = _clamp(raw, -limit, limit)
    return _rating(Decimal(current) + delta), delta


def _skill_targets(performance: MatchPerformance, weights: SportWeights) -> dict[str, Decimal]:
    """A 0–100 target per skill, from the stats that feed it.

    A skill no stat feeds is left exactly where it is. Nudging it towards the overall
    would make "why did my dribbling change?" unanswerable, and the honest answer is
    that nothing in this match said anything about it.
    """
    by_skill: dict[str, list[tuple[Decimal, Decimal]]] = {}
    for key, stat in weights.stats.items():
        if not stat.skill or stat.weight <= 0 or stat.benchmark <= 0:
            continue
        if key not in performance.stats:
            continue
        ratio = _clamp(_decimal(performance.stats[key]) / stat.benchmark, Decimal("0"), STAT_CAP)
        by_skill.setdefault(stat.skill, []).append((ratio, stat.weight))

    targets: dict[str, Decimal] = {}
    for skill, entries in by_skill.items():
        total = sum(weight for _, weight in entries)
        achieved = sum(ratio * weight for ratio, weight in entries) / (total * STAT_CAP)
        targets[skill] = STAT_BASELINE + (Decimal("100") - STAT_BASELINE) * achieved
    return targets


def _attribute_targets(
    performance: MatchPerformance, weights: SportWeights, participation: Decimal
) -> dict[str, Decimal]:
    """Only stamina has a signal in these sports, and only when minutes were recorded.

    Speed, agility and strength stay self-assessed until there is something real to move
    them with — inventing a number from goals would be worse than leaving it alone.
    """
    if performance.minutes is None:
        return {}
    return {"stamina": STAT_BASELINE + (Decimal("100") - STAT_BASELINE) * participation}


def rate_match(performance: MatchPerformance, *, provisional_matches: int = 10) -> RatingOutcome:
    """Apply one locked match to a player's ratings."""
    weights = weights_for(performance.sport_slug)
    scored = match_performance_score(performance)
    provisional = performance.matches_counted < provisional_matches
    # DOMAIN §8: a card the turf stands behind counts for more.
    multiplier = Decimal(str(1.5)) if performance.verified else Decimal("1")

    overall, overall_delta = _move(
        performance.current_overall,
        scored["score"],
        OVERALL_MOVEMENT,
        provisional=provisional,
        multiplier=multiplier,
    )

    skills: dict[str, int] = {}
    skill_deltas: dict[str, str] = {}
    for skill, target in _skill_targets(performance, weights).items():
        current = performance.current_skills.get(skill)
        if current is None:
            continue
        value, delta = _move(
            current, target, SKILL_MOVEMENT, provisional=provisional, multiplier=multiplier
        )
        skills[skill] = value
        skill_deltas[skill] = str(delta.quantize(Decimal("0.01")))

    attributes: dict[str, int] = {}
    attribute_deltas: dict[str, str] = {}
    for key, target in _attribute_targets(performance, weights, scored["participation"]).items():
        current = performance.current_attributes.get(key)
        if current is None:
            continue
        value, delta = _move(
            current, target, ATTRIBUTE_MOVEMENT, provisional=provisional, multiplier=multiplier
        )
        attributes[key] = value
        attribute_deltas[key] = str(delta.quantize(Decimal("0.01")))

    breakdown = {
        "performance": str(scored["score"].quantize(Decimal("0.01"))),
        "components": {
            name: str(value.quantize(Decimal("0.01")))
            for name, value in scored["components"].items()
        },
        "component_weights": {name: str(COMPONENT_WEIGHTS[name]) for name in scored["components"]},
        "participation": str(scored["participation"].quantize(Decimal("0.01"))),
        "card_penalty": str(scored["card_penalty"].quantize(Decimal("0.01"))),
        "motm_bonus": str(scored["motm_bonus"]),
        "provisional": provisional,
        "verified_multiplier": str(multiplier),
        "overall_delta": str(overall_delta.quantize(Decimal("0.01"))),
        "skill_deltas": skill_deltas,
        "attribute_deltas": attribute_deltas,
        "result": performance.result,
    }

    return RatingOutcome(overall=overall, skills=skills, attributes=attributes, breakdown=breakdown)
