"""Nightly jobs: leaderboards (DOMAIN §8)."""

from __future__ import annotations

import logging
from decimal import Decimal

from celery import shared_task
from django.conf import settings
from django.db import transaction
from django.utils.timezone import now

from apps.players.models import PlayerSportRating
from apps.sports.models import Sport, StatDefinition
from apps.turfs.models import Turf

from .models import LeaderboardEntry, RatingChange
from .selectors import period_start

logger = logging.getLogger(__name__)

#: The stat each sport's "top of the charts" board is built on.
HEADLINE_STAT = {"football": "goals", "futsal": "goals", "cricket": "runs", "badminton": "aces"}


def _changes(sport, turf, period):
    """The rating changes a board covers: this month's, or all of them."""
    changes = RatingChange.objects.filter(sport=sport).select_related("profile")
    if turf is not None:
        changes = changes.filter(match__booking__ground__turf=turf)
    if period == LeaderboardEntry.Period.MONTH:
        changes = changes.filter(played_at__date__gte=period_start(period))
    return changes


def _counted_rows(sport, turf, period, *, count):
    """Sum something per player over the matches a board covers.

    Counted from `RatingChange`, which stores each match exactly as it was rated. The
    track-record tables would be quicker, but they are career-long totals and "most MOTM
    **this month at Mirpur**" is neither.
    """
    by_profile: dict = {}
    for change in _changes(sport, turf, period):
        value = count(change.inputs or {})
        if not value:
            continue
        profile, running = by_profile.get(change.profile_id, (change.profile, Decimal("0")))
        by_profile[change.profile_id] = (profile, running + value)
    return sorted(by_profile.values(), key=lambda pair: pair[1], reverse=True)


def _rating_rows(sport, turf, period):
    """Highest rated — among the players the board covers, not everyone who ever played."""
    ratings = PlayerSportRating.objects.filter(sport=sport, matches_counted__gt=0).select_related(
        "profile"
    )
    if turf is not None or period == LeaderboardEntry.Period.MONTH:
        active = set(_changes(sport, turf, period).values_list("profile_id", flat=True))
        ratings = ratings.filter(profile_id__in=active)
    return [(rating.profile, Decimal(rating.overall)) for rating in ratings.order_by("-overall")]


def _motm_rows(sport, turf, period):
    return _counted_rows(
        sport, turf, period, count=lambda row: Decimal("1") if row.get("is_motm") else Decimal("0")
    )


def _win_rows(sport, turf, period):
    return _counted_rows(
        sport,
        turf,
        period,
        count=lambda row: Decimal("1") if row.get("result") == "win" else Decimal("0"),
    )


def _stat_rows(sport, turf, period, stat_key):
    """Top scorers, and each sport's equivalent."""
    return _counted_rows(
        sport,
        turf,
        period,
        count=lambda row: Decimal((row.get("stats") or {}).get(stat_key, "0")),
    )


def _write_board(*, sport, turf, metric, stat_key, period, rows) -> int:
    """Replace one board's rows. Rewritten whole, because ranks move together."""
    start = period_start(period)
    LeaderboardEntry.objects.filter(
        sport=sport, turf=turf, metric=metric, stat_key=stat_key, period=period, period_start=start
    ).delete()

    size = int(settings.LEADERBOARD_SIZE)
    entries = [
        LeaderboardEntry(
            sport=sport,
            turf=turf,
            metric=metric,
            stat_key=stat_key,
            period=period,
            period_start=start,
            profile=profile,
            rank=index,
            value=value,
        )
        for index, (profile, value) in enumerate(rows[:size], start=1)
        if value is not None
    ]
    LeaderboardEntry.objects.bulk_create(entries)
    return len(entries)


@shared_task(name="ratings.rebuild_leaderboards")
def rebuild_leaderboards() -> int:
    """Rewrite every board, platform-wide and per turf.

    Nightly rather than per request: a turf page reads these on every visit and they
    change once a day at most.
    """
    written = 0
    turfs = [None, *Turf.objects.filter(status=Turf.Status.APPROVED)]

    for sport in Sport.objects.filter(is_active=True):
        headline = HEADLINE_STAT.get(sport.slug)
        has_stat = bool(
            headline and StatDefinition.objects.filter(sport=sport, key=headline).exists()
        )
        for turf in turfs:
            for period in LeaderboardEntry.Period.values:
                with transaction.atomic():
                    written += _write_board(
                        sport=sport,
                        turf=turf,
                        metric=LeaderboardEntry.Metric.RATING,
                        stat_key="",
                        period=period,
                        rows=_rating_rows(sport, turf, period),
                    )
                    written += _write_board(
                        sport=sport,
                        turf=turf,
                        metric=LeaderboardEntry.Metric.MOTM,
                        stat_key="",
                        period=period,
                        rows=_motm_rows(sport, turf, period),
                    )
                    written += _write_board(
                        sport=sport,
                        turf=turf,
                        metric=LeaderboardEntry.Metric.WINS,
                        stat_key="",
                        period=period,
                        rows=_win_rows(sport, turf, period),
                    )
                    if has_stat:
                        written += _write_board(
                            sport=sport,
                            turf=turf,
                            metric=LeaderboardEntry.Metric.TOP_STAT,
                            stat_key=headline,
                            period=period,
                            rows=_stat_rows(sport, turf, period, headline),
                        )

    logger.info("Leaderboards rebuilt", extra={"rows": written, "at": str(now())})
    return written
