"""Turf endpoints: public discovery, the owner area, and the admin queue."""

from __future__ import annotations

from datetime import time, timedelta

import pytest
from django.contrib.gis.geos import Point
from rest_framework.test import APIClient

from apps.accounts.tests.factories import PlatformAdminFactory, UserFactory
from apps.core.utils import DHAKA, now
from apps.sports.models import SportFormat
from apps.turfs.availability import clear_booked_range_providers
from apps.turfs.models import Ground, Turf, TurfMembership
from apps.turfs.services import submit_turf_for_review

from .factories import (
    ApprovedTurfFactory,
    GroundFactory,
    TurfFactory,
    TurfMembershipFactory,
    open_all_week,
    price_everything,
)

pytestmark = pytest.mark.django_db

#: Real Dhaka neighbourhood centroids, so distance ordering means something.
DHANMONDI = (90.3760, 23.7465)
MIRPUR = (90.3654, 23.8223)
UTTARA = (90.3795, 23.8759)


@pytest.fixture(autouse=True)
def no_booking_providers():
    clear_booked_range_providers()
    yield
    clear_booked_range_providers()


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def player():
    return UserFactory()


@pytest.fixture
def admin():
    return PlatformAdminFactory()


@pytest.fixture
def football_5v5():
    return SportFormat.objects.get(sport__slug="football", slug="5v5")


def bookable_turf(*, slug: str, area: str, point, sport_format, owner=None) -> Turf:
    """An approved turf with hours, one priced active ground, and an owner."""
    turf = ApprovedTurfFactory(
        slug=slug, name=slug.replace("-", " ").title(), area=area, location=Point(*point, srid=4326)
    )
    open_all_week(turf, opens=time(0), closes=time(0))
    ground = GroundFactory(turf=turf, name=f"{area} Pitch", slug=f"{slug}-pitch")
    ground.sport_formats.set([sport_format])
    price_everything(ground, price="2000.00")
    TurfMembershipFactory(turf=turf, user=owner or UserFactory(), role=TurfMembership.Role.OWNER)
    return turf


class TestPublicDiscovery:
    def test_requires_authentication(self, client):
        assert client.get("/api/v1/turfs").status_code == 401

    def test_lists_approved_turfs(self, client, player, football_5v5):
        bookable_turf(slug="a-turf", area="Dhanmondi", point=DHANMONDI, sport_format=football_5v5)
        client.force_authenticate(player)

        response = client.get("/api/v1/turfs")
        assert response.status_code == 200
        assert [t["slug"] for t in response.data["results"]] == ["a-turf"]

    @pytest.mark.parametrize(
        "status",
        [
            Turf.Status.DRAFT,
            Turf.Status.PENDING_REVIEW,
            Turf.Status.REJECTED,
            Turf.Status.SUSPENDED,
        ],
    )
    def test_unapproved_turfs_never_appear(self, client, player, status):
        """Acceptance: unapproved turfs never appear in public endpoints."""
        TurfFactory(slug="hidden", status=status)
        client.force_authenticate(player)

        assert client.get("/api/v1/turfs").data["results"] == []
        assert client.get("/api/v1/turfs/hidden").status_code == 404

    def test_near_me_sorts_by_distance(self, client, player, football_5v5):
        """Acceptance: a player near Mirpur sees Mirpur turfs first."""
        bookable_turf(
            slug="dhanmondi", area="Dhanmondi", point=DHANMONDI, sport_format=football_5v5
        )
        bookable_turf(slug="mirpur", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        bookable_turf(slug="uttara", area="Uttara", point=UTTARA, sport_format=football_5v5)
        client.force_authenticate(player)

        # near= takes latitude,longitude the way a human writes it.
        response = client.get(f"/api/v1/turfs?near={MIRPUR[1]},{MIRPUR[0]}")
        assert [t["slug"] for t in response.data["results"]] == ["mirpur", "uttara", "dhanmondi"]

    def test_near_me_reports_the_distance(self, client, player, football_5v5):
        bookable_turf(slug="mirpur", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        client.force_authenticate(player)

        row = client.get(f"/api/v1/turfs?near={MIRPUR[1]},{MIRPUR[0]}").data["results"][0]
        assert row["distance_km"] == 0.0

    def test_latitude_and_longitude_are_not_swapped(self, client, player, football_5v5):
        """`near` is latitude,longitude — PostGIS wants the reverse.

        Getting this backwards silently puts Dhaka in the Indian Ocean, so the order is
        pinned here: the human order measures zero at the turf, and the PostGIS order is
        rejected outright because a longitude of 90.36 is not a valid latitude.
        """
        bookable_turf(slug="mirpur", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        client.force_authenticate(player)

        correct = client.get(f"/api/v1/turfs?near={MIRPUR[1]},{MIRPUR[0]}")
        assert correct.data["results"][0]["distance_km"] == 0.0

        swapped = client.get(f"/api/v1/turfs?near={MIRPUR[0]},{MIRPUR[1]}")
        assert swapped.status_code == 400
        assert "near" in swapped.data

    def test_radius_excludes_distant_turfs(self, client, player, football_5v5):
        bookable_turf(slug="mirpur", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        bookable_turf(slug="uttara", area="Uttara", point=UTTARA, sport_format=football_5v5)
        client.force_authenticate(player)

        response = client.get(f"/api/v1/turfs?near={MIRPUR[1]},{MIRPUR[0]}&radius_km=3")
        assert [t["slug"] for t in response.data["results"]] == ["mirpur"]

    def test_a_malformed_point_is_a_400(self, client, player):
        client.force_authenticate(player)
        assert client.get("/api/v1/turfs?near=not-a-point").status_code == 400
        assert client.get("/api/v1/turfs?near=999,999").status_code == 400

    def test_a_malformed_radius_is_a_400(self, client, player):
        client.force_authenticate(player)
        assert client.get("/api/v1/turfs?near=23.8,90.3&radius_km=soon").status_code == 400

    def test_without_a_point_results_are_alphabetical(self, client, player, football_5v5):
        """A player who declines geolocation must still get a usable list."""
        bookable_turf(slug="zebra", area="Uttara", point=UTTARA, sport_format=football_5v5)
        bookable_turf(slug="alpha", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        client.force_authenticate(player)

        response = client.get("/api/v1/turfs")
        assert [t["name"] for t in response.data["results"]] == ["Alpha", "Zebra"]
        assert response.data["results"][0]["distance_km"] is None

    def test_filters_by_sport(self, client, player, football_5v5):
        badminton = SportFormat.objects.get(sport__slug="badminton", slug="singles")
        bookable_turf(slug="football-only", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        bookable_turf(slug="badminton-only", area="Uttara", point=UTTARA, sport_format=badminton)
        client.force_authenticate(player)

        response = client.get("/api/v1/turfs?sport=badminton")
        assert [t["slug"] for t in response.data["results"]] == ["badminton-only"]

    def test_filters_by_area(self, client, player, football_5v5):
        bookable_turf(slug="mirpur", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        bookable_turf(slug="uttara", area="Uttara", point=UTTARA, sport_format=football_5v5)
        client.force_authenticate(player)

        assert len(client.get("/api/v1/turfs?area=mirpur").data["results"]) == 1

    def test_free_text_search(self, client, player, football_5v5):
        bookable_turf(slug="green-field", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        bookable_turf(slug="blue-court", area="Uttara", point=UTTARA, sport_format=football_5v5)
        client.force_authenticate(player)

        assert [t["slug"] for t in client.get("/api/v1/turfs?q=green").data["results"]] == [
            "green-field"
        ]

    def test_the_card_carries_the_cheapest_price(self, client, player, football_5v5):
        bookable_turf(slug="mirpur", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        client.force_authenticate(player)

        assert client.get("/api/v1/turfs").data["results"][0]["price_from"] == "2000.00"

    def test_detail_exposes_grounds_and_hours_but_not_status(self, client, player, football_5v5):
        bookable_turf(slug="mirpur", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        client.force_authenticate(player)

        data = client.get("/api/v1/turfs/mirpur").data
        assert len(data["grounds"]) == 1
        assert len(data["operating_hours"]) == 7
        # Review state is the owner's business, not a player's.
        assert "status" not in data
        assert "rejection_reason" not in data


class TestAvailabilityEndpoint:
    def test_returns_priced_slots(self, client, player, football_5v5):
        turf = bookable_turf(slug="mirpur", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        ground = turf.grounds.first()
        client.force_authenticate(player)
        tomorrow = (now().astimezone(DHAKA) + timedelta(days=1)).date()

        response = client.get(f"/api/v1/grounds/{ground.id}/availability?date={tomorrow}")
        assert response.status_code == 200
        assert response.data["slot_minutes"] == 60
        assert len(response.data["slots"]) == 24
        assert response.data["slots"][0]["price"] == "2000.00"
        assert response.data["slots"][0]["available"] is True

    def test_defaults_to_today(self, client, player, football_5v5):
        turf = bookable_turf(slug="mirpur", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        client.force_authenticate(player)

        response = client.get(f"/api/v1/grounds/{turf.grounds.first().id}/availability")
        assert response.status_code == 200
        assert response.data["date"] == str(now().astimezone(DHAKA).date())

    def test_a_malformed_date_is_a_400(self, client, player, football_5v5):
        turf = bookable_turf(slug="mirpur", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        client.force_authenticate(player)

        response = client.get(f"/api/v1/grounds/{turf.grounds.first().id}/availability?date=soon")
        assert response.status_code == 400

    def test_a_ground_at_an_unapproved_turf_is_a_404(self, client, player, football_5v5):
        """Availability would otherwise leak the existence of a venue still in review."""
        turf = bookable_turf(slug="mirpur", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        turf.status = Turf.Status.PENDING_REVIEW
        turf.save(update_fields=["status"])
        client.force_authenticate(player)

        response = client.get(f"/api/v1/grounds/{turf.grounds.first().id}/availability")
        assert response.status_code == 404

    def test_an_inactive_ground_is_a_404(self, client, player, football_5v5):
        turf = bookable_turf(slug="mirpur", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        ground = turf.grounds.first()
        Ground.objects.filter(pk=ground.pk).update(is_active=False)
        client.force_authenticate(player)

        assert client.get(f"/api/v1/grounds/{ground.id}/availability").status_code == 404


class TestOwnerArea:
    def test_register_a_turf(self, client, player):
        client.force_authenticate(player)
        response = client.post(
            "/api/v1/me/turfs",
            {
                "name": "New Turf",
                "address": "Road 5, Dhanmondi",
                "area": "Dhanmondi",
                "latitude": 23.7465,
                "longitude": 90.3760,
            },
            format="json",
        )

        assert response.status_code == 201
        assert response.data["status"] == "draft"
        assert response.data["my_role"] == "owner"

    def test_registration_validates_coordinates(self, client, player):
        client.force_authenticate(player)
        response = client.post(
            "/api/v1/me/turfs",
            {
                "name": "New Turf",
                "address": "Road 5",
                "area": "Dhanmondi",
                "latitude": 999,
                "longitude": 90.3760,
            },
            format="json",
        )
        assert response.status_code == 400

    def test_lists_only_my_turfs(self, client, player, football_5v5):
        mine = bookable_turf(
            slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5, owner=player
        )
        bookable_turf(slug="theirs", area="Uttara", point=UTTARA, sport_format=football_5v5)
        client.force_authenticate(player)

        response = client.get("/api/v1/me/turfs")
        assert [t["slug"] for t in response.data["results"]] == [mine.slug]

    def test_an_owner_sees_their_inactive_grounds(self, client, player):
        """The ground they most need to see is the one that is not bookable yet.

        A ground is created inactive and only becomes bookable once its open hours are
        fully priced — so filtering the owner's view to active grounds (as the *public*
        listing rightly does) hides the exact row they have to price and activate.
        """
        turf = TurfFactory(slug="mine")
        TurfMembershipFactory(turf=turf, user=player, role=TurfMembership.Role.OWNER)
        GroundFactory(turf=turf, name="Unpriced Pitch", slug="unpriced", is_active=False)
        client.force_authenticate(player)

        data = client.get("/api/v1/me/turfs/mine").data
        assert [g["name"] for g in data["grounds"]] == ["Unpriced Pitch"]
        assert data["grounds"][0]["is_active"] is False

    def test_players_still_only_see_bookable_grounds(self, client, player, football_5v5):
        """The flip side: the public listing must keep hiding inactive grounds."""
        turf = bookable_turf(slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        GroundFactory(turf=turf, name="Not Ready", slug="not-ready", is_active=False)
        client.force_authenticate(player)

        names = {g["name"] for g in client.get("/api/v1/turfs/mine").data["grounds"]}
        assert "Not Ready" not in names

    def test_a_reviewing_admin_sees_inactive_grounds(self, client, admin, football_5v5):
        """An unpriced ground is exactly the sort of thing a review should catch."""
        turf = bookable_turf(slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        # Priced (so the turf can be submitted at all) but not yet activated.
        price_everything(
            GroundFactory(turf=turf, name="Not Ready", slug="not-ready", is_active=False)
        )
        turf.status = Turf.Status.DRAFT
        turf.save(update_fields=["status"])
        submit_turf_for_review(turf=turf)
        client.force_authenticate(admin)

        names = {g["name"] for g in client.get("/api/v1/admin/turfs/mine").data["grounds"]}
        assert "Not Ready" in names

    def test_a_draft_turf_is_visible_to_its_owner(self, client, player):
        turf = TurfFactory(slug="draft-turf")
        TurfMembershipFactory(turf=turf, user=player, role=TurfMembership.Role.OWNER)
        client.force_authenticate(player)

        assert client.get("/api/v1/me/turfs/draft-turf").status_code == 200

    def test_staff_at_another_turf_cannot_read_mine(self, client, player, football_5v5):
        """Acceptance: staff of turf A can't touch turf B."""
        bookable_turf(
            slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5, owner=player
        )
        intruder = UserFactory()
        TurfMembershipFactory(
            turf=ApprovedTurfFactory(slug="elsewhere"),
            user=intruder,
            role=TurfMembership.Role.OWNER,
        )
        client.force_authenticate(intruder)

        assert client.get("/api/v1/me/turfs/mine").status_code == 404

    def test_a_cashier_can_see_the_turf_but_not_edit_it(self, client, football_5v5):
        """Acceptance: an invited cashier can sign in and see, but not edit, the turf."""
        turf = bookable_turf(slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        cashier = UserFactory()
        TurfMembershipFactory(turf=turf, user=cashier, role=TurfMembership.Role.CASHIER)
        client.force_authenticate(cashier)

        assert client.get("/api/v1/me/turfs/mine").status_code == 200
        assert client.get("/api/v1/me/turfs/mine").data["my_role"] == "cashier"
        assert client.patch("/api/v1/me/turfs/mine", {"name": "Hijacked"}).status_code == 403
        assert client.post("/api/v1/me/turfs/mine/grounds", {"name": "X"}).status_code == 403

    def test_update_moves_the_map_pin(self, client, player, football_5v5):
        bookable_turf(
            slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5, owner=player
        )
        client.force_authenticate(player)

        response = client.patch(
            "/api/v1/me/turfs/mine",
            {"latitude": UTTARA[1], "longitude": UTTARA[0]},
            format="json",
        )
        assert response.status_code == 200
        assert round(response.data["latitude"], 4) == round(UTTARA[1], 4)

    def test_add_a_ground_and_activate_it(self, client, player, football_5v5):
        turf = TurfFactory(slug="mine")
        open_all_week(turf)
        TurfMembershipFactory(turf=turf, user=player, role=TurfMembership.Role.OWNER)
        client.force_authenticate(player)

        created = client.post(
            "/api/v1/me/turfs/mine/grounds",
            {
                "name": "Pitch One",
                "max_players": 10,
                "slot_minutes": 60,
                "sport_format_ids": [str(football_5v5.id)],
            },
            format="json",
        )
        assert created.status_code == 201
        ground_id = created.data["id"]

        # Unpriced, so activation is refused and the error names the gap.
        refused = client.post(f"/api/v1/me/turfs/mine/grounds/{ground_id}/activate")
        assert refused.status_code == 400
        assert "price_rules" in refused.data

        priced = client.post(
            f"/api/v1/me/turfs/mine/grounds/{ground_id}/prices",
            {"weekdays": [], "start_time": "00:00", "end_time": "00:00", "price": "1500.00"},
            format="json",
        )
        assert priced.status_code == 201

        activated = client.post(f"/api/v1/me/turfs/mine/grounds/{ground_id}/activate")
        assert activated.status_code == 200
        assert activated.data["is_active"] is True

    def test_price_coverage_endpoint_reports_gaps(self, client, player, football_5v5):
        turf = TurfFactory(slug="mine")
        open_all_week(turf, opens=time(8), closes=time(22))
        TurfMembershipFactory(turf=turf, user=player, role=TurfMembership.Role.OWNER)
        ground = GroundFactory(turf=turf, is_active=False)
        client.force_authenticate(player)

        response = client.get(f"/api/v1/me/turfs/mine/grounds/{ground.id}/price-coverage")
        assert response.status_code == 200
        assert len(response.data) == 7
        assert response.data[0]["start_time"] == "08:00:00"

    def test_a_ground_cannot_be_created_on_someone_elses_turf(self, client, football_5v5):
        bookable_turf(slug="theirs", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        client.force_authenticate(UserFactory())

        response = client.post("/api/v1/me/turfs/theirs/grounds", {"name": "Mine now"})
        assert response.status_code == 404

    def test_opening_hours_crud(self, client, player):
        turf = TurfFactory(slug="mine")
        TurfMembershipFactory(turf=turf, user=player, role=TurfMembership.Role.OWNER)
        client.force_authenticate(player)

        created = client.post(
            "/api/v1/me/turfs/mine/hours",
            {"weekday": 4, "open_time": "18:00", "close_time": "02:00"},
            format="json",
        )
        assert created.status_code == 201
        assert created.data["crosses_midnight"] is True

        assert len(client.get("/api/v1/me/turfs/mine/hours").data["results"]) == 1
        assert client.delete(f"/api/v1/me/turfs/mine/hours/{created.data['id']}").status_code == 204

    def test_closures_must_end_after_they_start(self, client, player):
        turf = TurfFactory(slug="mine")
        TurfMembershipFactory(turf=turf, user=player, role=TurfMembership.Role.OWNER)
        client.force_authenticate(player)
        moment = now()

        response = client.post(
            "/api/v1/me/turfs/mine/closures",
            {"starts_at": moment.isoformat(), "ends_at": (moment - timedelta(hours=1)).isoformat()},
            format="json",
        )
        assert response.status_code == 400

    def test_submit_for_review(self, client, player, football_5v5):
        turf = bookable_turf(
            slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5, owner=player
        )
        turf.status = Turf.Status.DRAFT
        turf.save(update_fields=["status"])
        client.force_authenticate(player)

        response = client.post("/api/v1/me/turfs/mine/submit")
        assert response.status_code == 200
        assert response.data["status"] == "pending_review"

    def test_submit_reports_what_is_missing(self, client, player):
        turf = TurfFactory(slug="mine")
        TurfMembershipFactory(turf=turf, user=player, role=TurfMembership.Role.OWNER)
        client.force_authenticate(player)

        response = client.post("/api/v1/me/turfs/mine/submit")
        assert response.status_code == 400
        assert "grounds" in response.data


class TestStaffEndpoints:
    def test_owner_invites_a_cashier(self, client, player, football_5v5):
        bookable_turf(
            slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5, owner=player
        )
        client.force_authenticate(player)

        response = client.post(
            "/api/v1/me/turfs/mine/staff/invite",
            {"role": "cashier", "email": "cashier@example.com"},
            format="json",
        )
        assert response.status_code == 201
        assert response.data["status"] == "invited"

    def test_owner_cannot_invite_another_owner(self, client, player, football_5v5):
        bookable_turf(
            slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5, owner=player
        )
        client.force_authenticate(player)

        response = client.post(
            "/api/v1/me/turfs/mine/staff/invite",
            {"role": "owner", "email": "someone@example.com"},
            format="json",
        )
        assert response.status_code == 400

    def test_a_cashier_cannot_invite_staff(self, client, football_5v5):
        turf = bookable_turf(slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        cashier = UserFactory()
        TurfMembershipFactory(turf=turf, user=cashier, role=TurfMembership.Role.CASHIER)
        client.force_authenticate(cashier)

        response = client.post(
            "/api/v1/me/turfs/mine/staff/invite",
            {"role": "cashier", "email": "friend@example.com"},
            format="json",
        )
        assert response.status_code == 403

    def test_an_invitee_sees_and_accepts_the_invitation(self, client, player, football_5v5):
        bookable_turf(
            slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5, owner=player
        )
        cashier = UserFactory(email="cashier@example.com")
        client.force_authenticate(player)
        invite = client.post(
            "/api/v1/me/turfs/mine/staff/invite",
            {"role": "cashier", "email": cashier.email},
            format="json",
        ).data

        client.force_authenticate(cashier)
        assert [m["id"] for m in client.get("/api/v1/me/memberships").data["results"]] == [
            invite["id"]
        ]

        accepted = client.post(f"/api/v1/me/memberships/{invite['id']}/accept")
        assert accepted.status_code == 200
        assert accepted.data["status"] == "active"
        # And the turf is now reachable in their owner area.
        assert client.get("/api/v1/me/turfs/mine").status_code == 200

    def test_someone_else_cannot_accept_my_invitation(self, client, player, football_5v5):
        bookable_turf(
            slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5, owner=player
        )
        client.force_authenticate(player)
        invite = client.post(
            "/api/v1/me/turfs/mine/staff/invite",
            {"role": "cashier", "email": "cashier@example.com"},
            format="json",
        ).data

        client.force_authenticate(UserFactory(email="stranger@example.com"))
        response = client.post(f"/api/v1/me/memberships/{invite['id']}/accept")
        # Not even visible to them, let alone acceptable.
        assert response.status_code == 404

    def test_owner_removes_a_staff_member(self, client, player, football_5v5):
        turf = bookable_turf(
            slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5, owner=player
        )
        cashier = TurfMembershipFactory(turf=turf, role=TurfMembership.Role.CASHIER)
        client.force_authenticate(player)

        assert client.delete(f"/api/v1/me/turfs/mine/staff/{cashier.id}").status_code == 204
        cashier.refresh_from_db()
        assert cashier.status == TurfMembership.Status.REMOVED

    def test_the_owner_cannot_be_removed(self, client, player, football_5v5):
        turf = bookable_turf(
            slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5, owner=player
        )
        owner_membership = turf.memberships.get(user=player)
        client.force_authenticate(player)

        response = client.delete(f"/api/v1/me/turfs/mine/staff/{owner_membership.id}")
        assert response.status_code == 400

    def test_staff_listing(self, client, player, football_5v5):
        turf = bookable_turf(
            slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5, owner=player
        )
        TurfMembershipFactory(turf=turf, role=TurfMembership.Role.CASHIER)
        client.force_authenticate(player)

        roles = {m["role"] for m in client.get("/api/v1/me/turfs/mine/staff").data}
        assert roles == {"owner", "cashier"}


class TestAdminReview:
    def test_queue_is_admin_only(self, client, player):
        client.force_authenticate(player)
        assert client.get("/api/v1/admin/turfs").status_code == 403

    def test_queue_lists_pending_turfs_oldest_first(self, client, admin, football_5v5):
        first = bookable_turf(slug="first", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        second = bookable_turf(
            slug="second", area="Uttara", point=UTTARA, sport_format=football_5v5
        )
        for turf in (first, second):
            turf.status = Turf.Status.DRAFT
            turf.save(update_fields=["status"])
            submit_turf_for_review(turf=turf)
        client.force_authenticate(admin)

        assert [t["slug"] for t in client.get("/api/v1/admin/turfs").data["results"]] == [
            "first",
            "second",
        ]

    def test_approve_makes_the_turf_public(self, client, admin, player, football_5v5):
        turf = bookable_turf(slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        turf.status = Turf.Status.DRAFT
        turf.save(update_fields=["status"])
        submit_turf_for_review(turf=turf)

        client.force_authenticate(player)
        assert client.get("/api/v1/turfs/mine").status_code == 404

        client.force_authenticate(admin)
        assert client.post("/api/v1/admin/turfs/mine/approve").status_code == 200

        client.force_authenticate(player)
        assert client.get("/api/v1/turfs/mine").status_code == 200

    def test_reject_requires_a_reason(self, client, admin, football_5v5):
        turf = bookable_turf(slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        turf.status = Turf.Status.DRAFT
        turf.save(update_fields=["status"])
        submit_turf_for_review(turf=turf)
        client.force_authenticate(admin)

        assert client.post("/api/v1/admin/turfs/mine/reject", {}).status_code == 400

    def test_reject_tells_the_owner_why(self, client, admin, player, football_5v5):
        turf = bookable_turf(
            slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5, owner=player
        )
        turf.status = Turf.Status.DRAFT
        turf.save(update_fields=["status"])
        submit_turf_for_review(turf=turf)

        client.force_authenticate(admin)
        client.post("/api/v1/admin/turfs/mine/reject", {"reason": "Map pin is wrong."})

        client.force_authenticate(player)
        data = client.get("/api/v1/me/turfs/mine").data
        assert data["status"] == "rejected"
        assert data["rejection_reason"] == "Map pin is wrong."

    def test_suspend_pulls_it_from_the_listing(self, client, admin, player, football_5v5):
        bookable_turf(slug="mine", area="Mirpur", point=MIRPUR, sport_format=football_5v5)
        client.force_authenticate(admin)

        assert (
            client.post("/api/v1/admin/turfs/mine/suspend", {"reason": "Complaint"}).status_code
            == 200
        )

        client.force_authenticate(player)
        assert client.get("/api/v1/turfs/mine").status_code == 404

    def test_approving_a_draft_is_a_400(self, client, admin):
        TurfFactory(slug="draft-turf")
        client.force_authenticate(admin)
        assert client.post("/api/v1/admin/turfs/draft-turf/approve").status_code == 400


def test_amenities_endpoint(client, player):
    client.force_authenticate(player)
    response = client.get("/api/v1/amenities")
    assert response.status_code == 200
    assert {a["key"] for a in response.data} >= {"floodlights", "parking", "cafe"}
