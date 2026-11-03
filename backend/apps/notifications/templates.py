"""What each notification says (DOMAIN §11).

Separated from the service so adding a notification type is a data change, and so the
whole catalogue can be asserted against in one test — a missing template would otherwise
only surface when that transition first fires in production.

``title`` and ``body`` are ``str.format`` templates rendered against the context passed
to :func:`apps.notifications.services.notify`. ``email`` marks the types that are
important enough to leave the app for (DOMAIN §11: "email for key events").
"""

from __future__ import annotations

from typing import TypedDict

from .models import NotificationKind


class Template(TypedDict):
    title: str
    body: str
    email: bool


TEMPLATES: dict[str, Template] = {
    NotificationKind.BOOKING_CREATED: {
        "title": "Booking requested at {turf}",
        "body": "{ground} on {when}. We will let you know as soon as it is confirmed.",
        "email": False,
    },
    NotificationKind.BOOKING_PENDING_CONFIRMATION: {
        "title": "{player} wants {ground} on {when}",
        "body": "Confirm or decline before {expires}, or the slot is released.",
        "email": True,
    },
    NotificationKind.BOOKING_CONFIRMED: {
        "title": "Confirmed: {ground} at {turf}",
        "body": "{when}. Pay {price} in cash at the turf.",
        "email": True,
    },
    NotificationKind.BOOKING_EXPIRED: {
        "title": "Booking expired at {turf}",
        "body": "{ground} on {when} was not confirmed in time, so the slot was released.",
        "email": True,
    },
    NotificationKind.BOOKING_CANCELLED: {
        "title": "Cancelled: {ground} at {turf}",
        "body": "{when} was cancelled. {reason}",
        "email": True,
    },
    NotificationKind.BOOKING_PAID: {
        "title": "Payment received at {turf}",
        "body": "{price} for {ground} on {when}. Thank you.",
        "email": False,
    },
    NotificationKind.BOOKING_NO_SHOW: {
        "title": "Marked as a no-show at {turf}",
        "body": "{ground} on {when}. This affects your reliability score.",
        "email": True,
    },
    NotificationKind.BOOKING_COMPLETED: {
        "title": "Hope the game went well at {turf}",
        "body": "{ground} on {when} is complete.",
        "email": False,
    },
    NotificationKind.BOOKING_REMINDER: {
        "title": "Your game at {turf} starts soon",
        "body": "{ground} at {when}.",
        "email": False,
    },
}
