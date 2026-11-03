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
    NotificationKind.SQUAD_INVITE: {
        "title": "{inviter} invited you to {squad}",
        "body": "Accept to start getting their match invitations.",
        "email": True,
    },
    NotificationKind.SQUAD_JOINED: {
        "title": "{player} joined {squad}",
        "body": "",
        "email": False,
    },
    NotificationKind.MATCH_ADDED: {
        "title": "You are in: {sport} at {turf}",
        "body": "{ground} on {when}. Drop out from the match page if you cannot make it.",
        "email": False,
    },
    NotificationKind.MATCH_REMOVED: {
        "title": "Taken off the {sport} match at {turf}",
        "body": "{ground} on {when}.",
        "email": False,
    },
    NotificationKind.MATCH_PLAYER_LEFT: {
        "title": "{player} dropped out at {turf}",
        "body": "{when}. You still need {needed}.",
        "email": False,
    },
    NotificationKind.MATCH_JOIN_REQUEST: {
        "title": "{player} wants to join your {sport} match",
        "body": "{turf} on {when}. You still need {needed}.",
        "email": True,
    },
    NotificationKind.MATCH_JOIN_APPROVED: {
        "title": "You are in: {sport} at {turf}",
        "body": "{ground} on {when}. See you there.",
        "email": True,
    },
    NotificationKind.MATCH_JOIN_DECLINED: {
        "title": "Not this time: {sport} at {turf}",
        "body": "{when}. Have a look at the board for other matches.",
        "email": False,
    },
    NotificationKind.MATCH_INVITE: {
        "title": "Invitation: {sport} at {turf}",
        "body": "{ground} on {when}. Accept from the match page.",
        "email": True,
    },
    NotificationKind.MATCH_INVITE_PROPOSED: {
        "title": "{proposer} suggested {player}",
        "body": "For {sport} at {turf} on {when}. Approve to send them the invitation.",
        "email": True,
    },
    NotificationKind.MATCH_INVITE_ACCEPTED: {
        "title": "{player} is in",
        "body": "{sport} at {turf} on {when}. You still need {needed}.",
        "email": False,
    },
    NotificationKind.MATCH_INVITE_DECLINED: {
        "title": "{player} cannot make it",
        "body": "{sport} at {turf} on {when}. You still need {needed}.",
        "email": False,
    },
    NotificationKind.SCORECARD_SUBMITTED: {
        "title": "Check the score: {score}",
        "body": "{sport} at {turf}. Confirm or dispute it — silence counts as agreement.",
        "email": True,
    },
    NotificationKind.SCORECARD_DISPUTED: {
        "title": "The {score} scorecard is disputed",
        "body": "{sport} at {turf}. {reason}",
        "email": True,
    },
    NotificationKind.SCORECARD_LOCKED: {
        "title": "Final: {score}",
        "body": "{sport} at {turf}. Vote for man of the match and rate the players.",
        "email": False,
    },
    NotificationKind.MOTM_AWARDED: {
        "title": "You are man of the match",
        "body": "{sport} at {turf}, {score}. Nicely done.",
        "email": True,
    },
}
