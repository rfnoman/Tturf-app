"""Reminders (DOMAIN §10).

Every job here asks `should_send` first, so a player who switched a reminder off or is
asleep gets nothing. Each one is also idempotent per match or per week, because beat
runs them repeatedly and a nudge sent twice is worse than one sent late.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils.timezone import now

from apps.core.utils import to_dhaka
from apps.notifications.models import Notification, NotificationKind
from apps.notifications.services import notify

from .services import log_match_activity, should_send, streak_for, week_start, weekly_summary

logger = logging.getLogger(__name__)


def _already_told(*, user, kind: str, key: str) -> bool:
    """Has this player already had this exact nudge?"""
    return Notification.objects.filter(user=user, kind=kind, data__key=key).exists()


def _upcoming_matches(*, within: timedelta, at_least: timedelta = timedelta(0)):
    from apps.matches.models import Match, MatchStatus

    return (
        (
            Match.objects.filter(status=MatchStatus.UPCOMING)
            .select_related("booking__ground__turf", "sport")
            .prefetch_related("players__player")
        ),
        now() + at_least,
        now() + within,
    )


@shared_task(name="fitness.match_day_summary")
def match_day_summary() -> int:
    """The morning of a match: where, when, and what to bring."""
    matches, _floor, _ceiling = _upcoming_matches(within=timedelta(days=1))
    today = to_dhaka(now()).date()
    sent = 0

    for match in matches:
        if to_dhaka(match.starts_at).date() != today:
            continue
        key = f"match-day:{match.id}"

        for entry in match.players.all():
            player = entry.player
            if not should_send(player=player, kind="match_day") or _already_told(
                user=player, kind=NotificationKind.MATCH_DAY, key=key
            ):
                continue
            notify(
                user=player,
                kind=NotificationKind.MATCH_DAY,
                url=f"/matches/{match.id}",
                data={"key": key, "match_id": str(match.id)},
                sport=match.sport.name,
                turf=match.turf.name,
                when=to_dhaka(match.starts_at).strftime("%H:%M"),
            )
            sent += 1

    logger.info("Match-day summaries sent", extra={"count": sent})
    return sent


@shared_task(name="fitness.hydration_reminder")
def hydration_reminder() -> int:
    """Two hours out: drink something now, not at kick-off."""
    lead = timedelta(hours=float(settings.FITNESS_HYDRATION_LEAD_HOURS))
    matches, _floor, _ceiling = _upcoming_matches(within=lead)
    sent = 0

    for match in matches:
        if not (now() < match.starts_at <= now() + lead):
            continue
        key = f"hydration:{match.id}"

        for entry in match.players.all():
            player = entry.player
            if not should_send(player=player, kind="hydration") or _already_told(
                user=player, kind=NotificationKind.HYDRATION, key=key
            ):
                continue
            notify(
                user=player,
                kind=NotificationKind.HYDRATION,
                url="/store",
                data={"key": key, "match_id": str(match.id)},
                sport=match.sport.name,
                turf=match.turf.name,
            )
            sent += 1

    logger.info("Hydration reminders sent", extra={"count": sent})
    return sent


@shared_task(name="fitness.recovery_tip")
def recovery_tip() -> int:
    """After the final whistle: what the match cost, and what helps.

    Also the safety net for activity logging — a match nobody scored still happened, and
    this is where it becomes a log.
    """
    from apps.matches.models import Match, MatchStatus

    window_opens = now() - timedelta(hours=4)
    window_closes = now() - timedelta(minutes=30)
    finished = (
        Match.objects.filter(
            status__in=(MatchStatus.FINISHED, MatchStatus.UPCOMING),
            booking__time_range__endswith__gte=window_opens,
            booking__time_range__endswith__lte=window_closes,
        )
        .select_related("booking__ground__turf", "sport")
        .prefetch_related("players__player")
    )

    sent = 0
    for match in finished:
        # Logged here when no scorecard ever locked, so the week's totals are right
        # whether or not anybody filled the card in.
        log_match_activity(match=match)
        key = f"recovery:{match.id}"

        for entry in match.players.all():
            player = entry.player
            if not should_send(player=player, kind="recovery") or _already_told(
                user=player, kind=NotificationKind.RECOVERY, key=key
            ):
                continue

            log = player.activity.filter(match=match).first()
            notify(
                user=player,
                kind=NotificationKind.RECOVERY,
                url="/activity",
                data={"key": key, "match_id": str(match.id)},
                sport=match.sport.name,
                minutes=log.minutes if log else 0,
                calories=log.est_calories if log else 0,
            )
            sent += 1

    logger.info("Recovery tips sent", extra={"count": sent})
    return sent


@shared_task(name="fitness.weekly_recap")
def weekly_recap() -> int:
    """What the week came to, sent once as the new one starts."""
    from apps.accounts.models import User

    today = to_dhaka(now()).date()
    last_week = week_start(today) - timedelta(days=7)
    key = f"recap:{last_week.isoformat()}"
    sent = 0

    for player in User.objects.filter(activity__happened_on__gte=last_week).distinct():
        if not should_send(player=player, kind="weekly_recap") or _already_told(
            user=player, kind=NotificationKind.WEEKLY_RECAP, key=key
        ):
            continue

        summary = weekly_summary(player=player, day=last_week)
        if not summary["sessions"]:
            continue
        streak = streak_for(player=player, day=today)

        notify(
            user=player,
            kind=NotificationKind.WEEKLY_RECAP,
            url="/activity",
            data={"key": key},
            minutes=summary["minutes"],
            matches=summary["matches"],
            calories=summary["calories"],
            streak=streak["current"],
        )
        sent += 1

    logger.info("Weekly recaps sent", extra={"count": sent})
    return sent
