"""Rosters, join requests, the invite chain and squads (DOMAIN §6, DECISIONS D1)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from psycopg.types.range import TimestamptzRange

from apps.accounts.tests.factories import UserFactory
from apps.bookings.models import Booking, BookingVisibility
from apps.bookings.services import cancel_booking
from apps.core.utils import now
from apps.matches.models import (
    JoinRequest,
    MatchInvite,
    MatchPlayer,
    MatchStatus,
    SquadMembership,
)
from apps.matches.services import (
    add_player,
    advance_match_statuses,
    create_squad,
    decide_join_request,
    decide_proposed_invite,
    expire_started_matches,
    invite_player,
    invite_to_squad,
    leave_match,
    leave_squad,
    remove_player,
    remove_squad_member,
    request_to_join,
    respond_to_invite,
    respond_to_squad_invite,
    transfer_squad_leadership,
    withdraw_join_request,
)
from apps.notifications.models import Notification, NotificationKind

from .factories import make_match, make_squad

pytestmark = pytest.mark.django_db


@pytest.fixture
def booker():
    return UserFactory()


@pytest.fixture
def match(booker):
    return make_match(booker=booker)


class TestMatchCreation:
    def test_every_booking_creates_exactly_one_match(self, booker):
        """DOMAIN §6, wired through the booking hook."""
        match = make_match(booker=booker)
        assert match.booking.match == match
        assert Booking.objects.get(pk=match.booking_id).match.pk == match.pk

    def test_the_booker_is_on_the_roster(self, match, booker):
        assert [entry.player for entry in match.players.all()] == [booker]
        assert match.players.get().source == MatchPlayer.Source.BOOKER

    def test_capacity_is_players_per_side_times_two(self, booker):
        match = make_match(booker=booker, fmt="5v5", max_players=20)
        assert match.capacity == 10

    def test_the_ground_caps_the_capacity(self, booker):
        """A 7v7 format on a ground that holds 10 is a 10-player match."""
        match = make_match(booker=booker, fmt="7v7", max_players=10)
        assert match.capacity == 10

    def test_needed_counts_down_as_players_join(self, match):
        before = match.needed
        add_player(match=match, player=UserFactory(), source=MatchPlayer.Source.REQUEST)
        match.refresh_from_db()
        assert match.needed == before - 1

    def test_a_squad_booking_seeds_the_roster(self, booker):
        members = [UserFactory(), UserFactory()]
        squad = make_squad(leader=booker, members=members)
        match = make_match(booker=booker, squad=squad)

        assert match.players.count() == 3
        assert set(match.players.values_list("player_id", flat=True)) == {
            booker.id,
            *[m.id for m in members],
        }

    def test_squad_members_are_told_they_are_in(self, booker):
        member = UserFactory()
        squad = make_squad(leader=booker, members=[member])
        make_match(booker=booker, squad=squad)

        assert Notification.objects.filter(user=member, kind=NotificationKind.MATCH_ADDED).exists()

    def test_a_squad_bigger_than_the_match_fills_to_capacity(self, booker):
        members = [UserFactory() for _ in range(12)]
        squad = make_squad(leader=booker, members=members)
        match = make_match(booker=booker, squad=squad, fmt="5v5", max_players=10)

        assert match.capacity == 10
        assert match.players.count() == 10

    def test_a_walk_in_puts_nobody_on_the_roster(self):
        """The cashier is not playing, and the customer has no account."""
        from apps.bookings.services import create_booking
        from apps.bookings.tests.factories import bookable_ground, next_slot_start

        ground, sport_format = bookable_ground()
        staff = UserFactory()
        booking = create_booking(
            user=staff,
            ground=ground,
            start=next_slot_start(),
            sport_format=sport_format,
            booked_for_name="Karim",
        )
        assert booking.match.players.count() == 0

    def test_cancelling_the_booking_cancels_the_match(self, match, booker):
        cancel_booking(booking=match.booking, actor=booker)
        match.refresh_from_db()
        assert match.status == MatchStatus.CANCELLED

    def test_cancelling_expires_everything_pending(self, match, booker):
        joiner = UserFactory()
        request = request_to_join(match=match, user=joiner)

        cancel_booking(booking=match.booking, actor=booker)

        request.refresh_from_db()
        assert request.status == JoinRequest.Status.EXPIRED


class TestJoinRequests:
    def test_request_and_approve_puts_them_on_the_roster(self, match, booker):
        """Acceptance: B finds it, requests, A approves, B is on the roster."""
        joiner = UserFactory()
        request = request_to_join(match=match, user=joiner, message="I play left back")

        decide_join_request(request=request, approver=booker, approve=True)

        request.refresh_from_db()
        assert request.status == JoinRequest.Status.APPROVED
        assert match.players.filter(player=joiner).exists()
        assert Notification.objects.filter(
            user=joiner, kind=NotificationKind.MATCH_JOIN_APPROVED
        ).exists()

    def test_the_organiser_is_told_about_a_request(self, match, booker):
        request_to_join(match=match, user=UserFactory())
        assert Notification.objects.filter(
            user=booker, kind=NotificationKind.MATCH_JOIN_REQUEST
        ).exists()

    def test_declining_leaves_them_off(self, match, booker):
        joiner = UserFactory()
        request = request_to_join(match=match, user=joiner)

        decide_join_request(request=request, approver=booker, approve=False, note="Full up")

        request.refresh_from_db()
        assert request.status == JoinRequest.Status.DECLINED
        assert not match.players.filter(player=joiner).exists()

    def test_only_the_organiser_decides(self, match):
        request = request_to_join(match=match, user=UserFactory())
        with pytest.raises(ValidationError) as exc:
            decide_join_request(request=request, approver=UserFactory(), approve=True)
        assert "approver" in exc.value.message_dict

    def test_a_request_cannot_be_decided_twice(self, match, booker):
        request = request_to_join(match=match, user=UserFactory())
        decide_join_request(request=request, approver=booker, approve=True)
        with pytest.raises(ValidationError):
            decide_join_request(request=request, approver=booker, approve=False)

    def test_a_player_cannot_ask_twice(self, match):
        joiner = UserFactory()
        request_to_join(match=match, user=joiner)
        with pytest.raises(ValidationError) as exc:
            request_to_join(match=match, user=joiner)
        assert "already asked" in exc.value.message_dict["match"][0]

    def test_a_player_already_on_the_roster_cannot_ask(self, match, booker):
        with pytest.raises(ValidationError):
            request_to_join(match=match, user=booker)

    def test_a_full_match_blocks_requests(self, booker):
        """Acceptance: a full match blocks new requests."""
        match = make_match(booker=booker, fmt="5v5", max_players=2)
        add_player(match=match, player=UserFactory(), source=MatchPlayer.Source.REQUEST)
        match.refresh_from_db()

        with pytest.raises(ValidationError) as exc:
            request_to_join(match=match, user=UserFactory())
        assert "full" in exc.value.message_dict["match"][0]

    def test_a_clashing_match_blocks_a_request(self, booker):
        """One player cannot be in two places at once."""
        busy = UserFactory()
        first = make_match(booker=busy, hours_ahead=24)
        second = make_match(booker=booker, hours_ahead=24)
        # Both at the same hour on different grounds.
        Booking.objects.filter(pk=second.booking_id).update(
            time_range=Booking.objects.get(pk=first.booking_id).time_range
        )
        second.refresh_from_db()

        with pytest.raises(ValidationError) as exc:
            request_to_join(match=second, user=busy)
        assert "elsewhere" in exc.value.message_dict["match"][0]

    def test_a_started_match_blocks_requests(self, match):
        Booking.objects.filter(pk=match.booking_id).update(
            time_range=TimestamptzRange(now() - timedelta(hours=1), now() + timedelta(hours=1))
        )
        match.refresh_from_db()
        with pytest.raises(ValidationError):
            request_to_join(match=match, user=UserFactory())

    def test_withdrawing(self, match):
        joiner = UserFactory()
        request = request_to_join(match=match, user=joiner)
        withdraw_join_request(request=request, user=joiner)

        request.refresh_from_db()
        assert request.status == JoinRequest.Status.WITHDRAWN

    def test_only_the_asker_withdraws(self, match):
        request = request_to_join(match=match, user=UserFactory())
        with pytest.raises(ValidationError):
            withdraw_join_request(request=request, user=UserFactory())

    def test_approving_can_also_add_them_to_the_squad(self, booker):
        squad = make_squad(leader=booker, open_squad=True)
        match = make_match(booker=booker, squad=squad)
        joiner = UserFactory()
        request = request_to_join(match=match, user=joiner)

        decide_join_request(request=request, approver=booker, approve=True, add_to_squad=True)

        assert squad.memberships.filter(
            player=joiner, status=SquadMembership.Status.ACTIVE
        ).exists()


class TestCapacity:
    def test_the_last_spot_cannot_be_given_twice(self, booker):
        """Acceptance: two approvals for the last spot, only one succeeds."""
        match = make_match(booker=booker, fmt="5v5", max_players=2)
        first, second = UserFactory(), UserFactory()
        request_one = request_to_join(match=match, user=first)
        request_two = request_to_join(match=match, user=second)

        decide_join_request(request=request_one, approver=booker, approve=True)

        with pytest.raises(ValidationError) as exc:
            decide_join_request(request=request_two, approver=booker, approve=True)
        assert "full" in exc.value.message_dict["match"][0]

        match.refresh_from_db()
        assert match.players.count() == 2
        # The losing request stays pending, so the organiser can see why nothing happened.
        request_two.refresh_from_db()
        assert request_two.status == JoinRequest.Status.PENDING

    def test_add_player_refuses_beyond_capacity(self, booker):
        match = make_match(booker=booker, fmt="5v5", max_players=2)
        add_player(match=match, player=UserFactory(), source=MatchPlayer.Source.REQUEST)

        with pytest.raises(ValidationError):
            add_player(match=match, player=UserFactory(), source=MatchPlayer.Source.REQUEST)

    def test_add_player_refuses_a_duplicate(self, match, booker):
        with pytest.raises(ValidationError):
            add_player(match=match, player=booker, source=MatchPlayer.Source.REQUEST)

    def test_leaving_frees_a_spot(self, booker):
        match = make_match(booker=booker, fmt="5v5", max_players=2)
        joiner = UserFactory()
        add_player(match=match, player=joiner, source=MatchPlayer.Source.REQUEST)
        match.refresh_from_db()
        assert match.is_full

        leave_match(match=match, user=joiner)
        match.refresh_from_db()
        assert match.needed == 1


class TestLeaveAndRemove:
    def test_a_player_can_drop_out(self, match, booker):
        joiner = UserFactory()
        add_player(match=match, player=joiner, source=MatchPlayer.Source.REQUEST)

        leave_match(match=match, user=joiner)

        assert not match.players.filter(player=joiner).exists()
        assert Notification.objects.filter(
            user=booker, kind=NotificationKind.MATCH_PLAYER_LEFT
        ).exists()

    def test_the_organiser_cannot_drop_out(self, match, booker):
        with pytest.raises(ValidationError) as exc:
            leave_match(match=match, user=booker)
        assert "Cancel the booking" in exc.value.message_dict["match"][0]

    def test_the_organiser_removes_a_player(self, match, booker):
        joiner = UserFactory()
        add_player(match=match, player=joiner, source=MatchPlayer.Source.REQUEST)

        remove_player(match=match, actor=booker, player=joiner)

        assert not match.players.filter(player=joiner).exists()
        assert Notification.objects.filter(
            user=joiner, kind=NotificationKind.MATCH_REMOVED
        ).exists()

    def test_only_the_organiser_removes(self, match):
        joiner = UserFactory()
        add_player(match=match, player=joiner, source=MatchPlayer.Source.REQUEST)
        with pytest.raises(ValidationError):
            remove_player(match=match, actor=UserFactory(), player=joiner)

    def test_the_organiser_cannot_be_removed(self, match, booker):
        with pytest.raises(ValidationError):
            remove_player(match=match, actor=booker, player=booker)


class TestInviteChain:
    """DECISIONS D1: propose -> leader approves -> player accepts."""

    @pytest.fixture
    def closed(self):
        leader, member = UserFactory(), UserFactory()
        squad = make_squad(leader=leader, members=[member])
        match = make_match(booker=leader, squad=squad)
        return match, leader, member

    def test_the_full_chain(self, closed):
        """Acceptance: member proposes, leader approves, player accepts."""
        match, leader, member = closed
        guest = UserFactory()

        invite = invite_player(match=match, invited_by=member, player=guest)
        assert invite.status == MatchInvite.Status.PROPOSED
        # The guest is not told yet — the leader has not approved.
        assert not Notification.objects.filter(
            user=guest, kind=NotificationKind.MATCH_INVITE
        ).exists()
        assert Notification.objects.filter(
            user=leader, kind=NotificationKind.MATCH_INVITE_PROPOSED
        ).exists()

        decide_proposed_invite(invite=invite, leader=leader, approve=True)
        invite.refresh_from_db()
        assert invite.status == MatchInvite.Status.LEADER_APPROVED
        assert Notification.objects.filter(user=guest, kind=NotificationKind.MATCH_INVITE).exists()

        respond_to_invite(invite=invite, user=guest, accept=True)
        invite.refresh_from_db()
        assert invite.status == MatchInvite.Status.ACCEPTED
        assert match.players.filter(player=guest).exists()

    def test_the_leader_can_reject_a_proposal(self, closed):
        match, leader, member = closed
        guest = UserFactory()
        invite = invite_player(match=match, invited_by=member, player=guest)

        decide_proposed_invite(invite=invite, leader=leader, approve=False)

        invite.refresh_from_db()
        assert invite.status == MatchInvite.Status.REJECTED
        assert not match.players.filter(player=guest).exists()

    def test_only_the_leader_decides_a_proposal(self, closed):
        match, _, member = closed
        invite = invite_player(match=match, invited_by=member, player=UserFactory())
        with pytest.raises(ValidationError):
            decide_proposed_invite(invite=invite, leader=member, approve=True)

    def test_a_player_cannot_accept_before_the_leader_approves(self, closed):
        match, _, member = closed
        guest = UserFactory()
        invite = invite_player(match=match, invited_by=member, player=guest)

        with pytest.raises(ValidationError) as exc:
            respond_to_invite(invite=invite, user=guest, accept=True)
        assert "status" in exc.value.message_dict

    def test_only_the_invitee_responds(self, closed):
        match, leader, _ = closed
        invite = invite_player(match=match, invited_by=leader, player=UserFactory())
        with pytest.raises(ValidationError):
            respond_to_invite(invite=invite, user=UserFactory(), accept=True)

    def test_declining_leaves_them_off(self, closed):
        match, leader, _ = closed
        guest = UserFactory()
        invite = invite_player(match=match, invited_by=leader, player=guest)

        respond_to_invite(invite=invite, user=guest, accept=False)

        invite.refresh_from_db()
        assert invite.status == MatchInvite.Status.DECLINED
        assert not match.players.filter(player=guest).exists()

    def test_the_same_player_cannot_be_invited_twice(self, closed):
        match, leader, _ = closed
        guest = UserFactory()
        invite_player(match=match, invited_by=leader, player=guest)
        with pytest.raises(ValidationError):
            invite_player(match=match, invited_by=leader, player=guest)

    def test_a_full_match_cannot_be_invited_to(self, booker):
        match = make_match(booker=booker, fmt="5v5", max_players=2)
        add_player(match=match, player=UserFactory(), source=MatchPlayer.Source.REQUEST)
        match.refresh_from_db()

        with pytest.raises(ValidationError):
            invite_player(match=match, invited_by=booker, player=UserFactory())

    def test_accepting_into_a_clashing_slot_is_refused(self, booker):
        guest = UserFactory()
        theirs = make_match(booker=guest)
        match = make_match(booker=booker)
        Booking.objects.filter(pk=match.booking_id).update(
            time_range=Booking.objects.get(pk=theirs.booking_id).time_range
        )
        match.refresh_from_db()
        invite = invite_player(match=match, invited_by=booker, player=guest)

        with pytest.raises(ValidationError) as exc:
            respond_to_invite(invite=invite, user=guest, accept=True)
        assert "elsewhere" in exc.value.message_dict["match"][0]


class TestSquads:
    def test_create_makes_the_leader_a_member(self):
        leader = UserFactory()
        squad = create_squad(leader=leader, name="Dhanmondi FC")

        membership = squad.memberships.get()
        assert membership.player == leader
        assert membership.role == SquadMembership.Role.LEADER

    def test_names_can_repeat(self):
        first = create_squad(leader=UserFactory(), name="Dhanmondi FC")
        second = create_squad(leader=UserFactory(), name="Dhanmondi FC")
        assert first.slug != second.slug

    def test_invite_and_accept(self):
        leader, guest = UserFactory(), UserFactory()
        squad = create_squad(leader=leader, name="Squad")
        invite = invite_to_squad(squad=squad, invited_by=leader, player=guest)

        respond_to_squad_invite(invite=invite, user=guest, accept=True)

        assert squad.memberships.filter(player=guest, status=SquadMembership.Status.ACTIVE).exists()
        assert Notification.objects.filter(user=leader, kind=NotificationKind.SQUAD_JOINED).exists()

    def test_declining_leaves_them_out(self):
        leader, guest = UserFactory(), UserFactory()
        squad = create_squad(leader=leader, name="Squad")
        invite = invite_to_squad(squad=squad, invited_by=leader, player=guest)

        respond_to_squad_invite(invite=invite, user=guest, accept=False)

        assert not squad.memberships.filter(player=guest).exists()

    def test_an_outsider_cannot_invite(self):
        squad = create_squad(leader=UserFactory(), name="Squad")
        with pytest.raises(ValidationError):
            invite_to_squad(squad=squad, invited_by=UserFactory(), player=UserFactory())

    def test_a_member_can_invite(self):
        leader, member = UserFactory(), UserFactory()
        squad = make_squad(leader=leader, members=[member])
        invite = invite_to_squad(squad=squad, invited_by=member, player=UserFactory())
        assert invite.status == "pending"

    def test_leaving(self):
        leader, member = UserFactory(), UserFactory()
        squad = make_squad(leader=leader, members=[member])

        leave_squad(squad=squad, user=member)

        assert not squad.memberships.filter(
            player=member, status=SquadMembership.Status.ACTIVE
        ).exists()

    def test_the_leader_must_hand_over_before_leaving(self):
        leader = UserFactory()
        squad = make_squad(leader=leader, members=[UserFactory()])
        with pytest.raises(ValidationError) as exc:
            leave_squad(squad=squad, user=leader)
        assert "Transfer leadership" in exc.value.message_dict["leader"][0]

    def test_transfer_leadership(self):
        leader, member = UserFactory(), UserFactory()
        squad = make_squad(leader=leader, members=[member])

        transfer_squad_leadership(squad=squad, actor=leader, new_leader=member)

        squad.refresh_from_db()
        assert squad.leader == member
        assert squad.memberships.get(player=member).role == SquadMembership.Role.LEADER
        assert squad.memberships.get(player=leader).role == SquadMembership.Role.MEMBER

    def test_only_the_leader_hands_over(self):
        leader, member = UserFactory(), UserFactory()
        squad = make_squad(leader=leader, members=[member])
        with pytest.raises(ValidationError):
            transfer_squad_leadership(squad=squad, actor=member, new_leader=member)

    def test_leadership_cannot_go_to_an_outsider(self):
        leader = UserFactory()
        squad = make_squad(leader=leader)
        with pytest.raises(ValidationError):
            transfer_squad_leadership(squad=squad, actor=leader, new_leader=UserFactory())

    def test_the_leader_removes_a_member(self):
        leader, member = UserFactory(), UserFactory()
        squad = make_squad(leader=leader, members=[member])

        remove_squad_member(squad=squad, actor=leader, player=member)

        assert not squad.memberships.filter(
            player=member, status=SquadMembership.Status.ACTIVE
        ).exists()

    def test_the_leader_cannot_be_removed(self):
        leader = UserFactory()
        squad = make_squad(leader=leader)
        with pytest.raises(ValidationError):
            remove_squad_member(squad=squad, actor=leader, player=leader)

    def test_a_member_cannot_remove(self):
        leader, member = UserFactory(), UserFactory()
        other = UserFactory()
        squad = make_squad(leader=leader, members=[member, other])
        with pytest.raises(ValidationError):
            remove_squad_member(squad=squad, actor=member, player=other)

    def test_someone_who_left_can_be_invited_back(self):
        """The uniqueness constraint is partial for exactly this reason."""
        leader, member = UserFactory(), UserFactory()
        squad = make_squad(leader=leader, members=[member])
        leave_squad(squad=squad, user=member)

        invite = invite_to_squad(squad=squad, invited_by=leader, player=member)
        respond_to_squad_invite(invite=invite, user=member, accept=True)

        assert (
            squad.memberships.filter(player=member, status=SquadMembership.Status.ACTIVE).count()
            == 1
        )


class TestExpiry:
    def test_requests_expire_at_match_start(self, match):
        """DOMAIN §6: requests and invites expire when the match starts."""
        request = request_to_join(match=match, user=UserFactory())
        Booking.objects.filter(pk=match.booking_id).update(
            time_range=TimestamptzRange(now() - timedelta(minutes=5), now() + timedelta(hours=1))
        )

        assert expire_started_matches() >= 1

        request.refresh_from_db()
        assert request.status == JoinRequest.Status.EXPIRED

    def test_invites_expire_at_match_start(self, match, booker):
        invite = invite_player(match=match, invited_by=booker, player=UserFactory())
        Booking.objects.filter(pk=match.booking_id).update(
            time_range=TimestamptzRange(now() - timedelta(minutes=5), now() + timedelta(hours=1))
        )

        expire_started_matches()

        invite.refresh_from_db()
        assert invite.status == MatchInvite.Status.EXPIRED

    def test_a_future_match_is_untouched(self, match):
        request = request_to_join(match=match, user=UserFactory())
        assert expire_started_matches() == 0
        request.refresh_from_db()
        assert request.status == JoinRequest.Status.PENDING

    def test_statuses_advance_with_the_clock(self, match):
        Booking.objects.filter(pk=match.booking_id).update(
            time_range=TimestamptzRange(now() - timedelta(minutes=5), now() + timedelta(hours=1))
        )
        advance_match_statuses()
        match.refresh_from_db()
        assert match.status == MatchStatus.IN_PROGRESS

        Booking.objects.filter(pk=match.booking_id).update(
            time_range=TimestamptzRange(now() - timedelta(hours=2), now() - timedelta(hours=1))
        )
        advance_match_statuses()
        match.refresh_from_db()
        assert match.status == MatchStatus.FINISHED


def test_a_private_match_takes_no_requests(booker):
    match = make_match(booker=booker, visibility=BookingVisibility.PRIVATE)
    with pytest.raises(ValidationError) as exc:
        request_to_join(match=match, user=UserFactory())
    assert "not open to requests" in exc.value.message_dict["match"][0]
