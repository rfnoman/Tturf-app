"""Match board, match page and squad endpoints."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.bookings.models import BookingVisibility
from apps.bookings.tests.factories import next_slot_start
from apps.matches.services import (
    add_player,
    invite_player,
    request_to_join,
)
from apps.players.services import complete_onboarding, get_or_create_profile

from .factories import make_match, make_squad

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def booker():
    return UserFactory()


@pytest.fixture
def player():
    return UserFactory()


def onboard(user, sport: str = "football"):
    """Give a user a profile with a rating, so board averages are meaningful."""
    return complete_onboarding(
        user=user,
        data={
            "attributes": {"stamina": 60, "agility": 60, "speed": 60, "strength": 60},
            "sports": [{"sport": sport, "positions": [], "skills": {"finishing": 60}}],
        },
    )


class TestBoard:
    def test_requires_authentication(self, client):
        assert client.get("/api/v1/matches/board").status_code == 401

    def test_lists_open_public_matches(self, client, booker, player):
        make_match(booker=booker)
        client.force_authenticate(player)

        response = client.get("/api/v1/matches/board")
        assert response.status_code == 200
        assert len(response.data) == 1
        assert response.data[0]["needed"] == 9

    def test_hides_private_matches(self, client, booker, player):
        make_match(booker=booker, visibility=BookingVisibility.PRIVATE)
        client.force_authenticate(player)
        assert client.get("/api/v1/matches/board").data == []

    def test_hides_closed_squad_matches(self, client, booker, player):
        squad = make_squad(leader=booker)
        make_match(booker=booker, squad=squad)
        client.force_authenticate(player)
        assert client.get("/api/v1/matches/board").data == []

    def test_shows_open_squad_matches(self, client, booker, player):
        squad = make_squad(leader=booker, open_squad=True)
        make_match(booker=booker, squad=squad)
        client.force_authenticate(player)

        response = client.get("/api/v1/matches/board")
        assert len(response.data) == 1
        assert response.data[0]["squad"]["name"] == squad.name

    def test_hides_matches_i_am_already_in(self, client, booker):
        make_match(booker=booker)
        client.force_authenticate(booker)
        assert client.get("/api/v1/matches/board").data == []

    def test_hides_a_full_match(self, client, booker, player):
        match = make_match(booker=booker, fmt="5v5", max_players=2)
        add_player(match=match, player=UserFactory(), source="request")
        client.force_authenticate(player)
        assert client.get("/api/v1/matches/board").data == []

    def test_hides_a_cancelled_booking(self, client, booker, player):
        from apps.bookings.services import cancel_booking

        match = make_match(booker=booker)
        cancel_booking(booking=match.booking, actor=booker)
        client.force_authenticate(player)
        assert client.get("/api/v1/matches/board").data == []

    def test_filters_by_sport(self, client, booker, player):
        make_match(booker=booker, sport="football", fmt="5v5")
        make_match(booker=UserFactory(), sport="cricket", fmt="box")
        client.force_authenticate(player)

        response = client.get("/api/v1/matches/board?sport=cricket")
        assert [m["sport"]["slug"] for m in response.data] == ["cricket"]

    def test_filters_by_spots_left(self, client, booker, player):
        roomy = make_match(booker=booker, fmt="7v7", max_players=14)
        tight = make_match(booker=UserFactory(), fmt="5v5", max_players=4)
        client.force_authenticate(player)

        response = client.get("/api/v1/matches/board?needed_min=10")
        ids = [m["id"] for m in response.data]
        assert str(roomy.id) in ids
        assert str(tight.id) not in ids

    def test_filters_by_date(self, client, booker, player):
        soon = make_match(booker=booker, hours_ahead=24)
        make_match(booker=UserFactory(), hours_ahead=24 * 5)
        client.force_authenticate(player)
        from apps.core.utils import DHAKA

        day = soon.starts_at.astimezone(DHAKA).date()
        response = client.get(f"/api/v1/matches/board?date={day}")
        assert [m["id"] for m in response.data] == [str(soon.id)]

    def test_a_malformed_date_is_a_400(self, client, player):
        client.force_authenticate(player)
        assert client.get("/api/v1/matches/board?date=soon").status_code == 400

    def test_a_malformed_point_is_a_400(self, client, player):
        client.force_authenticate(player)
        assert client.get("/api/v1/matches/board?near=nope").status_code == 400

    def test_reports_the_average_rating(self, client, booker, player):
        onboard(booker)
        make_match(booker=booker)
        client.force_authenticate(player)

        assert client.get("/api/v1/matches/board").data[0]["average_rating"] is not None

    def test_an_unrated_roster_still_appears_in_a_filtered_board(self, client, booker, player):
        """A brand-new player's match is exactly what a browser wants to find."""
        make_match(booker=booker)
        client.force_authenticate(player)

        response = client.get("/api/v1/matches/board?rating_min=60&rating_max=90")
        assert len(response.data) == 1


class TestMatchPage:
    def test_the_roster_carries_profile_data(self, client, booker, player):
        onboard(booker)
        match = make_match(booker=booker)
        client.force_authenticate(player)

        data = client.get(f"/api/v1/matches/{match.id}").data
        assert len(data["roster"]) == 1
        assert data["roster"][0]["overall"] is not None
        assert data["roster"][0]["source"] == "booker"

    def test_a_private_match_is_a_404_for_an_outsider(self, client, booker, player):
        match = make_match(booker=booker, visibility=BookingVisibility.PRIVATE)
        client.force_authenticate(player)
        assert client.get(f"/api/v1/matches/{match.id}").status_code == 404

    def test_an_invitee_can_open_a_private_match(self, client, booker, player):
        match = make_match(booker=booker, visibility=BookingVisibility.PRIVATE)
        get_or_create_profile(player)
        invite_player(match=match, invited_by=booker, player=player)
        client.force_authenticate(player)

        data = client.get(f"/api/v1/matches/{match.id}").data
        assert data["my_invite_id"] is not None

    def test_the_organiser_sees_the_request_queue(self, client, booker, player):
        match = make_match(booker=booker)
        request_to_join(match=match, user=player, message="Keeper here")

        client.force_authenticate(booker)
        data = client.get(f"/api/v1/matches/{match.id}").data
        assert data["is_organiser"] is True
        assert len(data["pending_requests"]) == 1
        assert data["pending_requests"][0]["message"] == "Keeper here"

    def test_a_player_does_not_see_the_request_queue(self, client, booker, player):
        match = make_match(booker=booker)
        request_to_join(match=match, user=player)

        client.force_authenticate(player)
        data = client.get(f"/api/v1/matches/{match.id}").data
        assert data["is_organiser"] is False
        assert data["pending_requests"] == []

    def test_the_reason_a_player_cannot_request_is_explained(self, client, booker, player):
        match = make_match(booker=booker, fmt="5v5", max_players=2)
        add_player(match=match, player=UserFactory(), source="request")
        client.force_authenticate(player)

        data = client.get(f"/api/v1/matches/{match.id}").data
        assert data["can_request"] is False
        assert "full" in data["cannot_request_reason"]


class TestJoinFlow:
    def test_request_approve_and_appear_on_the_roster(self, client, booker, player):
        """Acceptance: A books publicly, B requests, A approves, B is on the roster."""
        match = make_match(booker=booker)

        client.force_authenticate(player)
        created = client.post(
            f"/api/v1/matches/{match.id}/request", {"message": "Left back"}, format="json"
        )
        assert created.status_code == 201

        client.force_authenticate(booker)
        decided = client.post(
            f"/api/v1/join-requests/{created.data['id']}/decide",
            {"approve": True},
            format="json",
        )
        assert decided.status_code == 200
        assert decided.data["status"] == "approved"

        client.force_authenticate(player)
        data = client.get(f"/api/v1/matches/{match.id}").data
        assert data["is_on_roster"] is True
        assert data["roster_count"] == 2

    def test_an_outsider_cannot_decide(self, client, booker, player):
        match = make_match(booker=booker)
        request = request_to_join(match=match, user=player)
        client.force_authenticate(UserFactory())

        response = client.post(
            f"/api/v1/join-requests/{request.id}/decide", {"approve": True}, format="json"
        )
        assert response.status_code == 400

    def test_withdrawing(self, client, booker, player):
        match = make_match(booker=booker)
        request = request_to_join(match=match, user=player)
        client.force_authenticate(player)

        response = client.post(f"/api/v1/join-requests/{request.id}/withdraw")
        assert response.status_code == 200
        assert response.data["status"] == "withdrawn"

    def test_leaving(self, client, booker, player):
        match = make_match(booker=booker)
        add_player(match=match, player=player, source="request")
        client.force_authenticate(player)

        response = client.post(f"/api/v1/matches/{match.id}/leave")
        assert response.status_code == 200
        assert response.data["is_on_roster"] is False

    def test_the_organiser_removes_a_player(self, client, booker, player):
        match = make_match(booker=booker)
        add_player(match=match, player=player, source="request")
        profile = get_or_create_profile(player)
        client.force_authenticate(booker)

        response = client.post(
            f"/api/v1/matches/{match.id}/remove-player",
            {"player_id": str(profile.id)},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["roster_count"] == 1

    def test_a_player_cannot_remove_others(self, client, booker, player):
        match = make_match(booker=booker)
        add_player(match=match, player=player, source="request")
        profile = get_or_create_profile(booker)
        client.force_authenticate(player)

        response = client.post(
            f"/api/v1/matches/{match.id}/remove-player",
            {"player_id": str(profile.id)},
            format="json",
        )
        assert response.status_code == 403


class TestInviteApi:
    def test_the_closed_squad_chain_over_http(self, client):
        """Acceptance: member proposes, leader approves, player accepts."""
        leader, member, guest = UserFactory(), UserFactory(), UserFactory()
        guest_profile = get_or_create_profile(guest)
        squad = make_squad(leader=leader, members=[member])
        match = make_match(booker=leader, squad=squad)

        client.force_authenticate(member)
        proposed = client.post(
            f"/api/v1/matches/{match.id}/invite",
            {"player_id": str(guest_profile.id)},
            format="json",
        )
        assert proposed.status_code == 201
        assert proposed.data["status"] == "proposed"

        client.force_authenticate(leader)
        approved = client.post(
            f"/api/v1/match-invites/{proposed.data['id']}/decide",
            {"approve": True},
            format="json",
        )
        assert approved.data["status"] == "leader_approved"

        client.force_authenticate(guest)
        assert [i["id"] for i in client.get("/api/v1/me/invites").data] == [proposed.data["id"]]

        accepted = client.post(
            f"/api/v1/match-invites/{proposed.data['id']}/respond",
            {"approve": True},
            format="json",
        )
        assert accepted.data["status"] == "accepted"

        data = client.get(f"/api/v1/matches/{match.id}").data
        assert data["is_on_roster"] is True

    def test_an_outsider_cannot_invite_over_http(self, client, booker):
        match = make_match(booker=booker)
        profile = get_or_create_profile(UserFactory())
        client.force_authenticate(UserFactory())

        response = client.post(
            f"/api/v1/matches/{match.id}/invite",
            {"player_id": str(profile.id)},
            format="json",
        )
        assert response.status_code == 400


class TestSquadApi:
    def test_create_and_read(self, client, player):
        client.force_authenticate(player)
        created = client.post(
            "/api/v1/squads",
            {"name": "Dhanmondi FC", "area": "Dhanmondi", "accepts_public_requests": True},
            format="json",
        )
        assert created.status_code == 201
        assert created.data["my_role"] == "leader"
        assert created.data["member_count"] == 1

        listed = client.get("/api/v1/squads")
        assert [s["slug"] for s in listed.data["results"]] == [created.data["slug"]]

    def test_only_the_leader_edits(self, client, player):
        leader = UserFactory()
        squad = make_squad(leader=leader, members=[player], name="Squad")
        client.force_authenticate(player)

        response = client.patch(f"/api/v1/squads/{squad.slug}", {"name": "Hijacked"}, format="json")
        assert response.status_code == 403

    def test_invite_accept_and_leave(self, client, player):
        leader = UserFactory()
        squad = make_squad(leader=leader, name="Squad")
        profile = get_or_create_profile(player)

        client.force_authenticate(leader)
        invite = client.post(
            f"/api/v1/squads/{squad.slug}/invite",
            {"player_id": str(profile.id)},
            format="json",
        )
        assert invite.status_code == 201

        client.force_authenticate(player)
        assert len(client.get("/api/v1/me/squad-invites").data) == 1

        accepted = client.post(
            f"/api/v1/squad-invites/{invite.data['id']}/respond",
            {"approve": True},
            format="json",
        )
        assert accepted.data["status"] == "accepted"
        assert client.get(f"/api/v1/squads/{squad.slug}").data["member_count"] == 2

        assert client.post(f"/api/v1/squads/{squad.slug}/leave").status_code == 204

    def test_the_leader_cannot_leave(self, client):
        leader = UserFactory()
        squad = make_squad(leader=leader)
        client.force_authenticate(leader)

        assert client.post(f"/api/v1/squads/{squad.slug}/leave").status_code == 400

    def test_transfer_leadership(self, client):
        leader, member = UserFactory(), UserFactory()
        squad = make_squad(leader=leader, members=[member])
        profile = get_or_create_profile(member)
        client.force_authenticate(leader)

        response = client.post(
            f"/api/v1/squads/{squad.slug}/transfer-leadership",
            {"player_id": str(profile.id)},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["leader_name"] == member.full_name


def test_my_matches(client, booker):
    make_match(booker=booker)
    client.force_authenticate(booker)

    response = client.get("/api/v1/matches/mine")
    assert response.status_code == 200
    assert len(response.data) == 1


def test_a_group_booking_requires_a_squad(client, booker):
    """Phase 03's booking endpoint now carries mode and squad (DOMAIN §6)."""
    from django.core.exceptions import ValidationError

    from apps.bookings.services import create_booking
    from apps.bookings.tests.factories import bookable_ground

    ground, sport_format = bookable_ground()
    with pytest.raises(ValidationError) as exc:
        create_booking(
            user=booker,
            ground=ground,
            start=next_slot_start(),
            sport_format=sport_format,
            mode="group",
        )
    assert "squad" in exc.value.message_dict


def test_booking_for_a_squad_you_are_not_in_is_refused(client, booker):
    from django.core.exceptions import ValidationError

    from apps.bookings.services import create_booking
    from apps.bookings.tests.factories import bookable_ground

    squad = make_squad(leader=UserFactory())
    ground, sport_format = bookable_ground()
    with pytest.raises(ValidationError):
        create_booking(
            user=booker,
            ground=ground,
            start=next_slot_start(),
            sport_format=sport_format,
            mode="group",
            squad=squad,
        )
