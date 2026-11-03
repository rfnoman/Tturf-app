"""The visibility × role matrix (DOMAIN §6, phase 04 step 5).

| Booking             | Visibility | Who can get in                                      |
|---------------------|------------|------------------------------------------------------|
| individual, public  | board      | anyone requests -> booker approves                    |
| individual, private | private    | booker invites                                        |
| group, open         | board      | anyone requests -> leader approves                    |
| group, closed       | squad      | member proposes -> leader approves -> player accepts  |

Every cell is asserted here for every role — outsider, squad member, leader, booker —
across *see*, *request*, and *invite*. Written before the services, which is what the
phase brief asks for, and it is the part of Phase 04 most likely to be got subtly wrong.
"""

from __future__ import annotations

import pytest

from apps.accounts.tests.factories import UserFactory
from apps.bookings.models import BookingVisibility
from apps.matches.models import MatchVisibility
from apps.matches.services import (
    can_request_to_join,
    can_view_match,
    invite_player,
    is_organiser,
)

from .factories import make_match, make_squad

pytestmark = pytest.mark.django_db


@pytest.fixture
def cast():
    """One account per role, reused across the matrix."""
    return {
        "booker": UserFactory(),
        "leader": UserFactory(),
        "member": UserFactory(),
        "outsider": UserFactory(),
    }


def build(kind: str, cast: dict):
    """Build one of the four DOMAIN §6 match shapes."""
    if kind == "individual_public":
        return make_match(booker=cast["booker"], visibility=BookingVisibility.PUBLIC)
    if kind == "individual_private":
        return make_match(booker=cast["booker"], visibility=BookingVisibility.PRIVATE)

    squad = make_squad(
        leader=cast["leader"],
        open_squad=(kind == "group_open"),
        members=[cast["member"]],
    )
    # The leader books for the squad, so the leader is also the organiser.
    return make_match(booker=cast["leader"], squad=squad)


# --- visibility is derived, never set -------------------------------------------------
@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        ("individual_public", MatchVisibility.BOARD),
        ("individual_private", MatchVisibility.PRIVATE),
        ("group_open", MatchVisibility.BOARD),
        ("group_closed", MatchVisibility.SQUAD),
    ],
)
def test_visibility_is_derived_from_the_booking_and_squad(kind, expected, cast):
    assert build(kind, cast).visibility == expected


# --- who can SEE it -------------------------------------------------------------------
SEE_MATRIX = [
    # kind,                 booker, leader, member, outsider
    ("individual_public", True, True, True, True),
    ("individual_private", True, False, False, False),
    # An open squad's match is on the board, so it is public to look at — the squad
    # flag controls who may *join*, not who may see.
    ("group_open", True, True, True, True),
    ("group_closed", False, True, True, False),
]


@pytest.mark.parametrize(("kind", "booker", "leader", "member", "outsider"), SEE_MATRIX)
def test_who_can_see_the_match(kind, booker, leader, member, outsider, cast):
    match = build(kind, cast)
    expected = {"booker": booker, "leader": leader, "member": member, "outsider": outsider}

    for role, allowed in expected.items():
        # In the group rows the "booker" cast member is an unrelated outsider, because
        # the leader did the booking — which is itself worth pinning down.
        assert can_view_match(match=match, user=cast[role]) is allowed, (
            f"{kind}: {role} should {'' if allowed else 'not '}see it"
        )


# --- who can REQUEST to join ----------------------------------------------------------
REQUEST_MATRIX = [
    # Only a board match takes requests, and only from somebody not already in it.
    ("individual_public", False, True, True, True),
    ("individual_private", False, False, False, False),
    ("group_open", True, False, False, True),
    ("group_closed", False, False, False, False),
]


@pytest.mark.parametrize(("kind", "booker", "leader", "member", "outsider"), REQUEST_MATRIX)
def test_who_can_request_to_join(kind, booker, leader, member, outsider, cast):
    match = build(kind, cast)
    expected = {"booker": booker, "leader": leader, "member": member, "outsider": outsider}

    for role, allowed in expected.items():
        can, reason = can_request_to_join(match=match, user=cast[role])
        assert can is allowed, f"{kind}: {role} -> {reason or 'allowed'}"


def test_the_organiser_is_the_leader_for_a_squad_match(cast):
    match = build("group_closed", cast)
    assert is_organiser(match=match, user=cast["leader"]) is True
    assert is_organiser(match=match, user=cast["member"]) is False


def test_the_organiser_is_the_booker_otherwise(cast):
    match = build("individual_public", cast)
    assert is_organiser(match=match, user=cast["booker"]) is True
    assert is_organiser(match=match, user=cast["outsider"]) is False


# --- who can INVITE, and where the invitation starts ----------------------------------
def test_the_booker_invites_straight_to_the_player(cast):
    match = build("individual_private", cast)
    invite = invite_player(match=match, invited_by=cast["booker"], player=cast["outsider"])
    # Nobody left to ask, so it skips `proposed`.
    assert invite.status == "leader_approved"


def test_an_outsider_cannot_invite(cast):
    from django.core.exceptions import ValidationError

    match = build("individual_public", cast)
    with pytest.raises(ValidationError):
        invite_player(match=match, invited_by=cast["outsider"], player=UserFactory())


def test_a_closed_squad_member_can_only_propose(cast):
    """DECISIONS D1: member proposes -> leader approves -> player accepts."""
    match = build("group_closed", cast)
    invite = invite_player(match=match, invited_by=cast["member"], player=cast["outsider"])
    assert invite.status == "proposed"


def test_the_leader_invites_straight_to_the_player(cast):
    match = build("group_closed", cast)
    invite = invite_player(match=match, invited_by=cast["leader"], player=cast["outsider"])
    assert invite.status == "leader_approved"


def test_a_non_member_cannot_propose_to_a_squad_match(cast):
    from django.core.exceptions import ValidationError

    match = build("group_closed", cast)
    with pytest.raises(ValidationError):
        invite_player(match=match, invited_by=cast["outsider"], player=UserFactory())


def test_an_invited_player_can_see_a_private_match(cast):
    """Otherwise they could not act on the invitation they were sent."""
    match = build("individual_private", cast)
    assert can_view_match(match=match, user=cast["outsider"]) is False

    invite_player(match=match, invited_by=cast["booker"], player=cast["outsider"])
    assert can_view_match(match=match, user=cast["outsider"]) is True


def test_a_proposed_player_cannot_see_the_match_yet(cast):
    """The leader has not approved, so there is nothing for them to act on."""
    match = build("group_closed", cast)
    invite_player(match=match, invited_by=cast["member"], player=cast["outsider"])
    assert can_view_match(match=match, user=cast["outsider"]) is False
