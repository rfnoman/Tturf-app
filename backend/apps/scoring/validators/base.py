"""The validator registry and the checks every sport gets (DOMAIN §7)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal

from apps.sports.models import StatDefinition


def number(value) -> str:
    """Render a Decimal the way a person writes it: 4, not 4.00, and 4.3 as 4.3.

    `:g` keeps a Decimal's trailing zeros (``Decimal("4.00")`` formats as ``4.00``), which
    reads like a rounding error in a message about goals.
    """
    if isinstance(value, Decimal):
        return f"{value.normalize():f}"
    return f"{value:g}"


@dataclass(frozen=True)
class ValidationIssue:
    """One thing wrong with a scorecard, addressed to whoever is entering it."""

    field: str
    message: str


@dataclass
class ScorecardData:
    """Everything a validator needs, already resolved.

    Passed as a value object rather than the ORM objects so validators stay pure and are
    trivial to unit-test with made-up numbers.
    """

    sport_slug: str
    team_a_score: int
    team_b_score: int
    #: ``{player_id: {stat_key: Decimal}}`` for every player given a stat.
    player_stats: dict[object, dict[str, Decimal]]
    #: ``{player_id: "A"|"B"}`` — which side each player is on.
    player_sides: dict[object, str]
    #: ``{"A": {stat_key: Decimal}, "B": {...}}`` for team-scope stats.
    team_stats: dict[str, dict[str, Decimal]] = field(default_factory=dict)
    #: The sport's definitions, keyed by stat key.
    definitions: dict[str, StatDefinition] = field(default_factory=dict)

    def total(self, stat_key: str, side: str) -> Decimal:
        """Sum one stat across a side's players."""
        return sum(
            (
                stats.get(stat_key, Decimal(0))
                for player_id, stats in self.player_stats.items()
                if self.player_sides.get(player_id) == side
            ),
            Decimal(0),
        )

    def score(self, side: str) -> int:
        return self.team_a_score if side == "A" else self.team_b_score


Validator = Callable[[ScorecardData], list[ValidationIssue]]

_validators: dict[str, Validator] = {}


def register(sport_slug: str):
    """Attach a validator to a sport. Later registrations replace earlier ones."""

    def decorator(func: Validator) -> Validator:
        _validators[sport_slug] = func
        return func

    return decorator


def registered_sports() -> list[str]:
    return sorted(_validators)


def generic_validator(data: ScorecardData) -> list[ValidationIssue]:
    """The checks every sport gets, including ones this codebase has never seen.

    Bounds only: a value outside a ``StatDefinition``'s min/max is wrong whatever the
    sport, and nothing else can be assumed about a sport nobody has written rules for.
    """
    issues: list[ValidationIssue] = []

    for player_id, stats in data.player_stats.items():
        for key, value in stats.items():
            definition = data.definitions.get(key)
            if definition is None:
                issues.append(
                    ValidationIssue(
                        field=key, message=f"{data.sport_slug} has no stat called “{key}”."
                    )
                )
                continue
            if value < definition.min_value:
                issues.append(
                    ValidationIssue(
                        field=key,
                        message=f"{definition.label} cannot be below {number(definition.min_value)}.",
                    )
                )
            if definition.max_value is not None and value > definition.max_value:
                issues.append(
                    ValidationIssue(
                        field=key,
                        message=f"{definition.label} cannot be above {number(definition.max_value)}.",
                    )
                )
            if definition.value_type == StatDefinition.ValueType.INT and value % 1 != 0:
                issues.append(
                    ValidationIssue(
                        field=key, message=f"{definition.label} must be a whole number."
                    )
                )

        if player_id not in data.player_sides:
            issues.append(
                ValidationIssue(
                    field="players",
                    message="Only players on a team sheet can be given stats.",
                )
            )

    return issues


def validate_scorecard(data: ScorecardData) -> list[ValidationIssue]:
    """Run the generic checks, then the sport's own.

    Both always run: a sport-specific validator adds rules, it does not replace the
    bounds check.
    """
    issues = generic_validator(data)
    sport_validator = _validators.get(data.sport_slug)
    if sport_validator is not None:
        issues.extend(sport_validator(data))
    return issues
