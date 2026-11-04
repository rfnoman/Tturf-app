"""Store jobs: cutoff reminders and late deliveries (DOMAIN §9)."""

from __future__ import annotations

import logging
from datetime import timedelta

from celery import shared_task
from django.conf import settings
from django.utils.timezone import now

from apps.core.utils import to_dhaka
from apps.notifications.models import NotificationKind
from apps.notifications.services import notify, notify_many

from .models import Fulfilment, Order, OrderStatus
from .services import cutoff_hours

logger = logging.getLogger(__name__)

#: How long before the cutoff a player is reminded. Long enough to act on, short enough
#: that nobody has forgotten they have a match.
REMINDER_LEAD_HOURS = 3


@shared_task(name="store.remind_before_cutoff")
def remind_before_cutoff() -> int:
    """ "Order by 5 AM to get it at the turf."

    Only to players on a match whose cutoff is coming up, and only once — the
    notification kind plus the match make that check cheap.
    """
    from apps.matches.models import Match, MatchStatus
    from apps.notifications.models import Notification

    hours = cutoff_hours()
    window_opens = now() + timedelta(hours=hours)
    window_closes = window_opens + timedelta(hours=REMINDER_LEAD_HOURS)

    matches = (
        Match.objects.filter(status=MatchStatus.UPCOMING)
        .select_related("booking__ground__turf", "sport")
        .prefetch_related("players__player")
    )

    sent = 0
    for match in matches:
        if not (window_opens <= match.starts_at <= window_closes):
            continue

        already = set(
            Notification.objects.filter(
                kind=NotificationKind.ORDER_CUTOFF_SOON, data__match_id=str(match.id)
            ).values_list("user_id", flat=True)
        )
        players = [entry.player for entry in match.players.all() if entry.player_id not in already]
        if not players:
            continue

        deadline = to_dhaka(match.starts_at - timedelta(hours=hours))
        notify_many(
            users=players,
            kind=NotificationKind.ORDER_CUTOFF_SOON,
            url="/store",
            data={"match_id": str(match.id)},
            cutoff=deadline.strftime("%I:%M %p").lstrip("0"),
            sport=match.sport.name,
            turf=match.turf.name,
            when=to_dhaka(match.starts_at).strftime("%a %d %b, %H:%M"),
        )
        sent += len(players)

    logger.info("Cutoff reminders sent", extra={"count": sent})
    return sent


@shared_task(name="store.flag_late_turf_deliveries")
def flag_late_turf_deliveries() -> int:
    """Orders promised to a turf that are not on their way with kick-off approaching.

    Tells the platform's admins, not the player: the player cannot fix it, and this is a
    warning that somebody needs to move.
    """
    from apps.accounts.models import User

    deadline = now() + timedelta(hours=int(settings.STORE_DELIVERY_WARNING_HOURS))
    late = Order.objects.filter(
        fulfilment=Fulfilment.DELIVER_TO_TURF,
        status__in=(OrderStatus.PLACED, OrderStatus.ACCEPTED, OrderStatus.PACKED),
        scheduled_for__lte=deadline,
    ).select_related("location", "match__booking__ground__turf")

    admins = list(User.objects.filter(is_platform_admin=True))
    count = 0
    for order in late:
        for admin in admins:
            notify(
                user=admin,
                kind=NotificationKind.ORDER_CUTOFF_SOON,
                url=f"/admin/orders?order={order.id}",
                cutoff=to_dhaka(order.scheduled_for).strftime("%H:%M")
                if order.scheduled_for
                else "",
                sport="Delivery",
                turf=order.match.turf.name if order.match else order.location.name,
                when="kick-off",
            )
        count += 1

    logger.info("Late turf deliveries flagged", extra={"count": count})
    return count
