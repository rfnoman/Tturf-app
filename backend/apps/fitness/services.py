"""Activity, goals, streaks and bundles (DOMAIN §10).

The week is the unit everything here is measured in, and it is a **Dhaka** week starting
on Saturday (DECISIONS D56). Every function that takes a date takes a Dhaka-local one,
because "did I play this week?" is a question about where the player is standing.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum

from apps.core.utils import now, to_dhaka

from .models import (
    ActivityLog,
    ActivitySource,
    Bundle,
    FitnessGoal,
    GoalType,
    ReminderPreference,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Weeks
# ---------------------------------------------------------------------------
def week_start(day: date | None = None) -> date:
    """The Saturday on or before `day`, in Dhaka terms (D56)."""
    day = day or to_dhaka(now()).date()
    starts_on = int(settings.FITNESS_WEEK_STARTS_ON)
    # `weekday()` is Monday=0 … Sunday=6; this walks back to the configured day.
    return day - timedelta(days=(day.weekday() - starts_on) % 7)


def week_range(day: date | None = None) -> tuple[date, date]:
    """The Saturday-to-Friday week containing `day`, inclusive both ends."""
    start = week_start(day)
    return start, start + timedelta(days=6)


# ---------------------------------------------------------------------------
# Calories
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Burn:
    calories: int
    is_estimate: bool


def estimate_calories(*, met, weight_kg, minutes: int) -> Burn:
    """`calories = MET × weight_kg × hours` (DOMAIN §10).

    A missing weight does not mean no answer: the fallback is used and the result is
    flagged, so the UI can say "estimated" rather than quietly inventing a number.
    """
    is_estimate = weight_kg is None
    weight = Decimal(
        str(weight_kg if weight_kg is not None else settings.FITNESS_FALLBACK_WEIGHT_KG)
    )
    hours = Decimal(minutes) / Decimal("60")
    calories = Decimal(str(met)) * weight * hours

    return Burn(
        calories=int(calories.quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
        is_estimate=is_estimate,
    )


# ---------------------------------------------------------------------------
# Logging activity
# ---------------------------------------------------------------------------
def _minutes_of(match) -> int:
    booking = match.booking
    delta = booking.time_range.upper - booking.time_range.lower
    return max(1, int(delta.total_seconds() // 60))


@transaction.atomic
def log_match_activity(*, scorecard=None, match=None) -> list[ActivityLog]:
    """Turn one played match into a log for everybody who was there.

    Takes a scorecard when there is one (the Phase 05 hook) and a match when there is
    not — a game that finished without anybody filling in the score still happened, and
    the player still ran around for an hour.
    """
    match = match or (scorecard.match if scorecard is not None else None)
    if match is None:
        return []

    minutes = _minutes_of(match)
    played_on = to_dhaka(match.starts_at).date()
    met = match.sport.met_value
    logs: list[ActivityLog] = []

    for entry in match.players.select_related("player__player_profile"):
        # A player marked absent did not do the exercise.
        if entry.attended is False:
            continue
        if ActivityLog.objects.filter(player=entry.player, match=match).exists():
            continue

        profile = getattr(entry.player, "player_profile", None)
        burn = estimate_calories(
            met=met,
            weight_kg=profile.weight_kg if profile and profile.weight_kg else None,
            minutes=minutes,
        )
        logs.append(
            ActivityLog.objects.create(
                player=entry.player,
                sport=match.sport,
                match=match,
                source=ActivitySource.MATCH,
                happened_on=played_on,
                minutes=minutes,
                est_calories=burn.calories,
                is_estimate=burn.is_estimate,
            )
        )

    logger.info("Activity logged", extra={"match": str(match.id), "players": len(logs)})
    return logs


@transaction.atomic
def log_manual_activity(
    *, player, minutes: int, happened_on: date | None = None, sport=None, note: str = ""
) -> ActivityLog:
    """A gym session, a run — something the player did that the app did not see."""
    if minutes <= 0:
        raise ValidationError({"minutes": "How long did it take?"})
    if minutes > 24 * 60:
        raise ValidationError({"minutes": "That is more than a day."})

    happened_on = happened_on or to_dhaka(now()).date()
    if happened_on > to_dhaka(now()).date():
        raise ValidationError({"happened_on": "That is in the future."})

    profile = getattr(player, "player_profile", None)
    # No sport means general exercise; 6 METs is a brisk, unspecified workout.
    met = sport.met_value if sport is not None else Decimal("6")
    burn = estimate_calories(
        met=met,
        weight_kg=profile.weight_kg if profile and profile.weight_kg else None,
        minutes=minutes,
    )

    return ActivityLog.objects.create(
        player=player,
        sport=sport,
        source=ActivitySource.MANUAL,
        happened_on=happened_on,
        minutes=minutes,
        est_calories=burn.calories,
        is_estimate=burn.is_estimate,
        note=note[:200],
    )


# ---------------------------------------------------------------------------
# Summaries, streaks and goals
# ---------------------------------------------------------------------------
def weekly_summary(*, player, day: date | None = None) -> dict:
    """What a player has done this week, and how it splits by sport."""
    start, end = week_range(day)
    logs = ActivityLog.objects.filter(player=player, happened_on__gte=start, happened_on__lte=end)

    totals = logs.aggregate(
        minutes=Sum("minutes"), calories=Sum("est_calories"), sessions=Count("id")
    )
    by_sport = (
        logs.exclude(sport__isnull=True)
        .values("sport__slug", "sport__name")
        .annotate(minutes=Sum("minutes"), sessions=Count("id"))
        .order_by("-minutes")
    )

    return {
        "week_start": start,
        "week_end": end,
        "minutes": totals["minutes"] or 0,
        "calories": totals["calories"] or 0,
        "sessions": totals["sessions"] or 0,
        "matches": logs.filter(source=ActivitySource.MATCH).count(),
        "by_sport": [
            {
                "sport": row["sport__name"],
                "slug": row["sport__slug"],
                "minutes": row["minutes"],
                "sessions": row["sessions"],
            }
            for row in by_sport
        ],
        "is_estimate": logs.filter(is_estimate=True).exists(),
    }


def streak_for(*, player, day: date | None = None) -> dict:
    """Weeks in a row with at least one match (DOMAIN §10).

    Counted on **matches**, not on manual logs: the streak is about turning up to play,
    and a player could otherwise keep one alive by typing in a walk.
    """
    weeks = {
        week_start(row)
        for row in ActivityLog.objects.filter(
            player=player, source=ActivitySource.MATCH
        ).values_list("happened_on", flat=True)
    }
    if not weeks:
        return {"current": 0, "best": 0, "played_this_week": False}

    this_week = week_start(day)
    last_week = this_week - timedelta(days=7)

    # A streak that includes this week counts from here; one that ended last week is
    # still alive until this week is over, which is what keeps it worth saving.
    current = 0
    cursor = this_week if this_week in weeks else last_week
    while cursor in weeks:
        current += 1
        cursor -= timedelta(days=7)

    best = 0
    for start in sorted(weeks):
        if start - timedelta(days=7) in weeks:
            continue
        run = 0
        cursor = start
        while cursor in weeks:
            run += 1
            cursor += timedelta(days=7)
        best = max(best, run)

    return {"current": current, "best": best, "played_this_week": this_week in weeks}


def goal_progress(*, player, day: date | None = None) -> list[dict]:
    """Each active goal with where the week has got to."""
    summary = weekly_summary(player=player, day=day)
    achieved = {
        GoalType.MATCHES: summary["matches"],
        GoalType.MINUTES: summary["minutes"],
        GoalType.CALORIES: summary["calories"],
    }

    return [
        {
            "id": goal.id,
            "type": goal.type,
            "label": goal.get_type_display(),
            "target": goal.target,
            "achieved": achieved.get(goal.type, 0),
            "percent": min(100, round(achieved.get(goal.type, 0) / goal.target * 100))
            if goal.target
            else 0,
        }
        for goal in FitnessGoal.objects.filter(player=player, is_active=True)
    ]


@transaction.atomic
def set_goal(*, player, type: str, target: int) -> FitnessGoal | None:
    """Set or replace a weekly goal.

    A target of zero **retires** the goal and returns None rather than raising: zero is
    how the UI says "I do not want this one any more", and refusing it would mean a
    player could set a goal and never be rid of it.
    """
    if type not in GoalType.values:
        raise ValidationError({"type": "Unknown goal."})

    if target <= 0:
        FitnessGoal.objects.filter(player=player, type=type).update(is_active=False)
        return None

    goal, _ = FitnessGoal.objects.update_or_create(
        player=player, type=type, defaults={"target": target, "is_active": True}
    )
    return goal


# ---------------------------------------------------------------------------
# Bundles
# ---------------------------------------------------------------------------
def bundle_source(bundle: Bundle):
    """Where a bundle's items are bought from: whoever owns the bundle.

    A turf bundle comes off that turf's shelf and a platform bundle from the warehouse,
    with no third option. The products themselves belong to one owner or the other —
    a turf's "Banana" is a different row from the platform's — so a platform bundle
    could never be picked from a turf's shelf however much we wanted it to.
    """
    from apps.inventory.services import location_for_turf, warehouse

    if bundle.turf_id is not None:
        return location_for_turf(bundle.turf)
    return warehouse()


@transaction.atomic
def add_bundle_to_cart(*, player, bundle: Bundle) -> dict:
    """One tap, the whole kit (DOMAIN §10).

    Partial stock does not fail the whole bundle: the player gets what is there and is
    told what was missing. Refusing the lot because the bananas ran out would be the
    worse answer.
    """
    from apps.inventory.models import StockItem
    from apps.store.services import add_to_cart

    location = bundle_source(bundle)
    added, missing = [], []

    for item in bundle.items.select_related("product"):
        stock = StockItem.objects.filter(location=location, product=item.product).first()
        if stock is None or stock.available <= 0:
            missing.append(item.product.name)
            continue

        quantity = min(item.quantity, stock.available)
        try:
            add_to_cart(user=player, stock_item=stock, quantity=quantity)
        except ValidationError:
            missing.append(item.product.name)
            continue

        added.append({"product": item.product.name, "quantity": quantity})
        if quantity < item.quantity:
            missing.append(f"{item.product.name} (only {quantity})")

    if not added:
        raise ValidationError({"bundle": "Nothing in this bundle is in stock there right now."})

    return {"added": added, "missing": missing, "source_id": location.id}


def suggested_bundles(*, player, match=None, limit: int = 3) -> list[Bundle]:
    """What to offer before a match: that turf's bundles for the sport, then the
    platform's."""
    bundles = Bundle.objects.filter(is_active=True).prefetch_related("items__product")
    if match is not None:
        bundles = bundles.filter(models_q(turf=match.turf) | models_q(turf__isnull=True)).filter(
            models_q(sport=match.sport) | models_q(sport__isnull=True)
        )
        return list(bundles.order_by("turf_id", "occasion")[:limit])
    return list(bundles.filter(turf__isnull=True).order_by("occasion")[:limit])


def models_q(**kwargs):

    return Q(**kwargs)


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------
def reminder_preference(player) -> ReminderPreference:
    preference, _ = ReminderPreference.objects.get_or_create(player=player)
    return preference


def in_quiet_hours(preference: ReminderPreference, *, moment=None) -> bool:
    """Is it the middle of the night for this player?

    Quiet hours wrap midnight, which is the only case that matters: 22:00–07:00 is one
    window, not two.
    """
    from datetime import time as time_type

    moment = to_dhaka(moment or now()).time()

    def parse(value, fallback):
        if value is not None:
            return value
        hour, minute = (int(part) for part in fallback.split(":"))
        return time_type(hour, minute)

    start = parse(preference.quiet_from, settings.FITNESS_QUIET_FROM)
    end = parse(preference.quiet_until, settings.FITNESS_QUIET_UNTIL)

    if start == end:
        return False
    if start < end:
        return start <= moment < end
    return moment >= start or moment < end


def should_send(*, player, kind: str, moment=None) -> bool:
    """One check for every reminder: does the player want it, and is it a decent hour?"""
    preference = reminder_preference(player)
    if not preference.wants(kind):
        return False
    return not in_quiet_hours(preference, moment=moment)
