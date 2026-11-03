"""Turf and membership state machines, and price-coverage enforcement (DOMAIN §1, §4)."""

from __future__ import annotations

from datetime import time

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.tests.factories import PlatformAdminFactory, UserFactory
from apps.sports.models import SportFormat
from apps.turfs.models import Ground, Turf, TurfMembership
from apps.turfs.services import (
    accept_staff_invite,
    activate_ground,
    approve_turf,
    create_ground,
    create_turf,
    has_turf_role,
    invite_staff,
    membership_for,
    reject_turf,
    remove_staff,
    submit_turf_for_review,
    suspend_turf,
    unique_turf_slug,
    validate_price_coverage,
)

from .factories import (
    DHANMONDI,
    ApprovedTurfFactory,
    GroundFactory,
    PriceRuleFactory,
    TurfFactory,
    TurfMembershipFactory,
    open_all_week,
    price_everything,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return UserFactory()


@pytest.fixture
def admin():
    return PlatformAdminFactory()


@pytest.fixture
def football_5v5():
    return SportFormat.objects.get(sport__slug="football", slug="5v5")


def make_submittable(turf: Turf, football_5v5) -> Ground:
    """A turf with hours, a ground and full price coverage — ready for review."""
    open_all_week(turf)
    ground = GroundFactory(turf=turf, is_active=False)
    ground.sport_formats.set([football_5v5])
    price_everything(ground)
    return ground


class TestCreateTurf:
    def test_starts_as_a_draft_owned_by_the_creator(self, owner):
        from django.contrib.gis.geos import Point

        turf = create_turf(
            owner=owner,
            name="Champions Turf",
            address="Road 1",
            area="Dhanmondi",
            location=Point(*DHANMONDI, srid=4326),
        )

        assert turf.status == Turf.Status.DRAFT
        membership = TurfMembership.objects.get(turf=turf, user=owner)
        assert membership.role == TurfMembership.Role.OWNER
        assert membership.status == TurfMembership.Status.ACTIVE

    def test_requires_a_name(self, owner):
        from django.contrib.gis.geos import Point

        with pytest.raises(ValidationError) as exc:
            create_turf(
                owner=owner,
                name="   ",
                address="Road 1",
                area="Dhanmondi",
                location=Point(*DHANMONDI, srid=4326),
            )
        assert "name" in exc.value.message_dict

    def test_two_turfs_may_share_a_name(self, owner):
        """ "Champions Turf" in two areas is entirely normal."""
        from django.contrib.gis.geos import Point

        first = create_turf(
            owner=owner,
            name="Champions Turf",
            address="A",
            area="Mirpur",
            location=Point(*DHANMONDI, srid=4326),
        )
        second = create_turf(
            owner=UserFactory(),
            name="Champions Turf",
            address="B",
            area="Uttara",
            location=Point(*DHANMONDI, srid=4326),
        )
        assert first.slug != second.slug
        assert second.slug == "champions-turf-2"


class TestSubmitForReview:
    def test_a_complete_turf_can_be_submitted(self, football_5v5):
        turf = TurfFactory()
        make_submittable(turf, football_5v5)

        submit_turf_for_review(turf=turf)

        turf.refresh_from_db()
        assert turf.status == Turf.Status.PENDING_REVIEW
        assert turf.submitted_at is not None

    def test_refuses_a_turf_with_no_grounds(self, football_5v5):
        """An admin should never open a queue item with nothing in it."""
        turf = TurfFactory()
        open_all_week(turf)
        with pytest.raises(ValidationError) as exc:
            submit_turf_for_review(turf=turf)
        assert "grounds" in exc.value.message_dict

    def test_refuses_a_turf_with_no_opening_hours(self, football_5v5):
        turf = TurfFactory()
        GroundFactory(turf=turf)
        with pytest.raises(ValidationError) as exc:
            submit_turf_for_review(turf=turf)
        assert "operating_hours" in exc.value.message_dict

    def test_refuses_a_ground_with_unpriced_hours(self, football_5v5):
        turf = TurfFactory()
        open_all_week(turf, opens=time(8), closes=time(22))
        ground = GroundFactory(turf=turf, name="Pitch A")
        PriceRuleFactory(
            ground=ground, weekdays=[], start_time=time(8), end_time=time(12), price="1000.00"
        )

        with pytest.raises(ValidationError) as exc:
            submit_turf_for_review(turf=turf)
        assert "Pitch A" in exc.value.message_dict["price_rules"][0]

    def test_a_rejected_turf_can_be_resubmitted(self, admin, football_5v5):
        turf = TurfFactory()
        make_submittable(turf, football_5v5)
        submit_turf_for_review(turf=turf)
        reject_turf(turf=turf, reviewer=admin, reason="Photos are too dark.")

        submit_turf_for_review(turf=turf)

        turf.refresh_from_db()
        assert turf.status == Turf.Status.PENDING_REVIEW
        # The old reason must not linger on a turf now awaiting a fresh decision.
        assert turf.rejection_reason == ""

    def test_an_approved_turf_cannot_be_resubmitted(self, football_5v5):
        turf = ApprovedTurfFactory()
        make_submittable(turf, football_5v5)
        with pytest.raises(ValidationError):
            submit_turf_for_review(turf=turf)


class TestReview:
    def test_approve(self, admin, football_5v5):
        turf = TurfFactory()
        make_submittable(turf, football_5v5)
        submit_turf_for_review(turf=turf)

        approve_turf(turf=turf, reviewer=admin)

        turf.refresh_from_db()
        assert turf.status == Turf.Status.APPROVED
        assert turf.is_public is True
        assert turf.reviewed_by == admin

    def test_reject_requires_a_reason(self, admin, football_5v5):
        turf = TurfFactory()
        make_submittable(turf, football_5v5)
        submit_turf_for_review(turf=turf)

        with pytest.raises(ValidationError) as exc:
            reject_turf(turf=turf, reviewer=admin, reason="  ")
        assert "reason" in exc.value.message_dict

    def test_reject_records_the_reason(self, admin, football_5v5):
        turf = TurfFactory()
        make_submittable(turf, football_5v5)
        submit_turf_for_review(turf=turf)

        reject_turf(turf=turf, reviewer=admin, reason="Address does not match the map pin.")

        turf.refresh_from_db()
        assert turf.status == Turf.Status.REJECTED
        assert "map pin" in turf.rejection_reason

    def test_a_draft_cannot_be_approved(self, admin):
        with pytest.raises(ValidationError):
            approve_turf(turf=TurfFactory(), reviewer=admin)

    def test_suspend_pulls_an_approved_turf(self, admin):
        turf = ApprovedTurfFactory()
        suspend_turf(turf=turf, reviewer=admin, reason="Complaints about the surface.")

        turf.refresh_from_db()
        assert turf.status == Turf.Status.SUSPENDED
        assert turf.is_public is False

    def test_a_suspended_turf_can_be_reinstated(self, admin):
        turf = ApprovedTurfFactory()
        suspend_turf(turf=turf, reviewer=admin)
        approve_turf(turf=turf, reviewer=admin)

        turf.refresh_from_db()
        assert turf.status == Turf.Status.APPROVED

    def test_a_draft_cannot_be_suspended(self, admin):
        with pytest.raises(ValidationError):
            suspend_turf(turf=TurfFactory(), reviewer=admin)


class TestStaff:
    def test_invite_by_email_for_someone_with_no_account(self, owner):
        turf = ApprovedTurfFactory()
        membership = invite_staff(
            turf=turf,
            invited_by=owner,
            role=TurfMembership.Role.CASHIER,
            email="New.Cashier@example.com",
        )

        assert membership.status == TurfMembership.Status.INVITED
        assert membership.user is None
        # Normalised, so the acceptance check is a straight comparison.
        assert membership.invited_email == "new.cashier@example.com"

    def test_invite_links_an_existing_account_immediately(self, owner):
        cashier = UserFactory(email="cashier@example.com")
        membership = invite_staff(
            turf=ApprovedTurfFactory(),
            invited_by=owner,
            role=TurfMembership.Role.CASHIER,
            email="Cashier@example.com",
        )
        assert membership.user == cashier

    def test_invite_requires_a_contact(self, owner):
        with pytest.raises(ValidationError) as exc:
            invite_staff(
                turf=ApprovedTurfFactory(), invited_by=owner, role=TurfMembership.Role.CASHIER
            )
        assert "email" in exc.value.message_dict

    def test_ownership_cannot_be_handed_out_by_invitation(self, owner):
        with pytest.raises(ValidationError) as exc:
            invite_staff(
                turf=ApprovedTurfFactory(),
                invited_by=owner,
                role=TurfMembership.Role.OWNER,
                email="someone@example.com",
            )
        assert "role" in exc.value.message_dict

    def test_an_unknown_role_is_refused(self, owner):
        with pytest.raises(ValidationError):
            invite_staff(
                turf=ApprovedTurfFactory(),
                invited_by=owner,
                role="janitor",
                email="someone@example.com",
            )

    def test_the_same_person_cannot_be_invited_twice(self, owner):
        turf = ApprovedTurfFactory()
        cashier = UserFactory(email="cashier@example.com")
        invite_staff(turf=turf, invited_by=owner, role="cashier", email=cashier.email)

        with pytest.raises(ValidationError):
            invite_staff(turf=turf, invited_by=owner, role="manager", email=cashier.email)

    def test_accepting_activates_the_membership(self, owner):
        cashier = UserFactory(email="cashier@example.com")
        membership = invite_staff(
            turf=ApprovedTurfFactory(),
            invited_by=owner,
            role="cashier",
            email=cashier.email,
        )

        accept_staff_invite(membership=membership, user=cashier)

        membership.refresh_from_db()
        assert membership.status == TurfMembership.Status.ACTIVE
        assert membership.accepted_at is not None

    def test_someone_else_cannot_accept_a_targeted_invite(self, owner):
        """A leaked membership id must not be enough to join a turf's staff."""
        cashier = UserFactory(email="cashier@example.com")
        membership = invite_staff(
            turf=ApprovedTurfFactory(),
            invited_by=owner,
            role="cashier",
            email=cashier.email,
        )

        with pytest.raises(ValidationError) as exc:
            accept_staff_invite(membership=membership, user=UserFactory())
        assert "user" in exc.value.message_dict

    def test_an_email_invite_is_matched_on_the_address(self, owner):
        membership = invite_staff(
            turf=ApprovedTurfFactory(),
            invited_by=owner,
            role="cashier",
            email="future@example.com",
        )
        stranger = UserFactory(email="someone.else@example.com")

        with pytest.raises(ValidationError):
            accept_staff_invite(membership=membership, user=stranger)

        arrival = UserFactory(email="future@example.com")
        accept_staff_invite(membership=membership, user=arrival)
        assert membership.user == arrival

    def test_an_invite_cannot_be_accepted_twice(self, owner):
        cashier = UserFactory(email="cashier@example.com")
        membership = invite_staff(
            turf=ApprovedTurfFactory(), invited_by=owner, role="cashier", email=cashier.email
        )
        accept_staff_invite(membership=membership, user=cashier)

        with pytest.raises(ValidationError):
            accept_staff_invite(membership=membership, user=cashier)

    def test_removing_keeps_the_row_for_history(self, owner):
        """Phase 03's "confirmed by" must still resolve to a person after they leave."""
        membership = TurfMembershipFactory(role=TurfMembership.Role.CASHIER)
        remove_staff(membership=membership)

        membership.refresh_from_db()
        assert membership.status == TurfMembership.Status.REMOVED
        assert TurfMembership.objects.filter(pk=membership.pk).exists()

    def test_the_owner_cannot_be_removed(self):
        membership = TurfMembershipFactory(role=TurfMembership.Role.OWNER)
        with pytest.raises(ValidationError) as exc:
            remove_staff(membership=membership)
        assert "role" in exc.value.message_dict

    def test_removing_twice_is_a_no_op(self):
        membership = TurfMembershipFactory(role=TurfMembership.Role.CASHIER)
        remove_staff(membership=membership)
        assert remove_staff(membership=membership).status == TurfMembership.Status.REMOVED

    def test_a_removed_person_can_be_invited_back(self, owner):
        """The uniqueness constraint is partial for exactly this reason."""
        turf = ApprovedTurfFactory()
        cashier = UserFactory(email="cashier@example.com")
        first = invite_staff(turf=turf, invited_by=owner, role="cashier", email=cashier.email)
        remove_staff(membership=first)

        second = invite_staff(turf=turf, invited_by=owner, role="manager", email=cashier.email)
        assert second.pk != first.pk


class TestMembershipLookups:
    def test_membership_for_finds_an_active_role(self):
        membership = TurfMembershipFactory()
        assert membership_for(turf=membership.turf, user=membership.user) == membership

    def test_a_removed_membership_is_not_found(self):
        membership = TurfMembershipFactory(role=TurfMembership.Role.CASHIER)
        remove_staff(membership=membership)
        assert membership_for(turf=membership.turf, user=membership.user) is None

    def test_an_invited_membership_does_not_grant_access_yet(self):
        membership = TurfMembershipFactory(status=TurfMembership.Status.INVITED)
        assert membership_for(turf=membership.turf, user=membership.user) is None

    def test_has_turf_role_is_scoped_to_one_turf(self):
        """Staff at turf A must not be staff at turf B."""
        membership = TurfMembershipFactory()
        other = ApprovedTurfFactory(slug="other-turf")

        assert has_turf_role(turf=membership.turf, user=membership.user, roles=("owner",)) is True
        assert has_turf_role(turf=other, user=membership.user, roles=("owner",)) is False

    def test_a_cashier_does_not_hold_the_owner_role(self):
        membership = TurfMembershipFactory(role=TurfMembership.Role.CASHIER)
        assert has_turf_role(turf=membership.turf, user=membership.user, roles=("owner",)) is False


class TestGroundActivation:
    def test_activates_a_fully_priced_ground(self, football_5v5):
        turf = ApprovedTurfFactory()
        ground = make_submittable(turf, football_5v5)

        activate_ground(ground=ground)

        ground.refresh_from_db()
        assert ground.is_active is True

    def test_refuses_an_unpriced_ground(self, football_5v5):
        turf = ApprovedTurfFactory()
        open_all_week(turf, opens=time(8), closes=time(22))
        ground = GroundFactory(turf=turf, is_active=False)
        ground.sport_formats.set([football_5v5])
        PriceRuleFactory(
            ground=ground, weekdays=[], start_time=time(8), end_time=time(12), price="1000.00"
        )

        with pytest.raises(ValidationError) as exc:
            activate_ground(ground=ground)
        assert "price_rules" in exc.value.message_dict

        ground.refresh_from_db()
        assert ground.is_active is False

    def test_refuses_a_ground_with_no_sport(self, football_5v5):
        turf = ApprovedTurfFactory()
        open_all_week(turf)
        ground = GroundFactory(turf=turf, is_active=False)
        price_everything(ground)

        with pytest.raises(ValidationError) as exc:
            activate_ground(ground=ground)
        assert "sport_formats" in exc.value.message_dict

    def test_refuses_when_the_turf_has_no_hours(self, football_5v5):
        ground = GroundFactory(turf=ApprovedTurfFactory(), is_active=False)
        ground.sport_formats.set([football_5v5])
        price_everything(ground)

        with pytest.raises(ValidationError) as exc:
            activate_ground(ground=ground)
        assert "operating_hours" in exc.value.message_dict

    def test_validate_price_coverage_names_the_gap(self):
        turf = ApprovedTurfFactory()
        open_all_week(turf, opens=time(8), closes=time(22))
        ground = GroundFactory(turf=turf)
        PriceRuleFactory(
            ground=ground, weekdays=[], start_time=time(8), end_time=time(20), price="1.00"
        )

        with pytest.raises(ValidationError) as exc:
            validate_price_coverage(ground=ground)
        assert "20:00–22:00" in exc.value.message_dict["price_rules"][0]


def test_create_ground_requires_a_name():
    with pytest.raises(ValidationError):
        create_ground(turf=ApprovedTurfFactory(), name="  ")


def test_ground_slugs_are_unique_per_turf_only():
    turf_a, turf_b = ApprovedTurfFactory(slug="a"), ApprovedTurfFactory(slug="b")
    first = create_ground(turf=turf_a, name="Main Pitch", max_players=10)
    same_name_elsewhere = create_ground(turf=turf_b, name="Main Pitch", max_players=10)
    second_at_a = create_ground(turf=turf_a, name="Main Pitch", max_players=10)

    assert first.slug == same_name_elsewhere.slug == "main-pitch"
    assert second_at_a.slug == "main-pitch-2"


def test_unique_turf_slug_falls_back_for_unsluggable_names():
    assert unique_turf_slug("!!!") == "turf"
