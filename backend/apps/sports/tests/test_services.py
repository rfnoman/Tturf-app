"""``SportProposal`` state machine (DOMAIN §2)."""

from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError

from apps.accounts.tests.factories import PlatformAdminFactory, UserFactory
from apps.sports.models import Sport, SportProposal
from apps.sports.services import (
    approve_sport_proposal,
    create_sport_proposal,
    merge_sport_proposal,
    reject_sport_proposal,
    unique_sport_slug,
)

from .factories import SportProposalFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return UserFactory()


@pytest.fixture
def admin():
    return PlatformAdminFactory()


class TestCreate:
    def test_creates_a_pending_proposal(self, owner):
        proposal = create_sport_proposal(
            user=owner, name="Beach Volleyball", description="Sand court next door."
        )
        assert proposal.status == SportProposal.Status.PENDING
        assert proposal.proposed_by == owner
        assert proposal.is_open

    def test_strips_whitespace(self, owner):
        proposal = create_sport_proposal(user=owner, name="  Kabaddi  ")
        assert proposal.name == "Kabaddi"

    def test_rejects_a_blank_name(self, owner):
        with pytest.raises(ValidationError) as exc:
            create_sport_proposal(user=owner, name="   ")
        assert "name" in exc.value.message_dict

    def test_rejects_a_sport_already_in_the_catalogue(self, owner):
        with pytest.raises(ValidationError) as exc:
            create_sport_proposal(user=owner, name="football")
        assert "Football" in exc.value.message_dict["name"][0]

    def test_rejects_a_duplicate_pending_proposal_from_the_same_user(self, owner):
        create_sport_proposal(user=owner, name="Kabaddi")
        with pytest.raises(ValidationError):
            create_sport_proposal(user=owner, name="kabaddi")

    def test_allows_the_same_name_from_a_different_user(self, owner):
        create_sport_proposal(user=owner, name="Kabaddi")
        other = create_sport_proposal(user=UserFactory(), name="Kabaddi")
        assert other.status == SportProposal.Status.PENDING


class TestApprove:
    def test_creates_the_sport_and_closes_the_proposal(self, owner, admin):
        proposal = SportProposalFactory(proposed_by=owner, name="Kabaddi")

        sport = approve_sport_proposal(proposal=proposal, reviewer=admin)

        proposal.refresh_from_db()
        assert sport.name == "Kabaddi"
        assert sport.slug == "kabaddi"
        assert proposal.status == SportProposal.Status.APPROVED
        assert proposal.merged_into == sport
        assert proposal.reviewed_by == admin
        assert proposal.reviewed_at is not None

    def test_new_sport_starts_inactive_until_an_admin_configures_it(self, admin):
        """It has no formats, skills or stats yet, so it must not reach onboarding."""
        proposal = SportProposalFactory(name="Kabaddi")
        sport = approve_sport_proposal(proposal=proposal, reviewer=admin)
        assert sport.is_active is False

    def test_admin_can_correct_the_name_and_set_a_met_value(self, admin):
        proposal = SportProposalFactory(name="kabadi")
        sport = approve_sport_proposal(
            proposal=proposal, reviewer=admin, name="Kabaddi", met_value="6.50", icon="🤼"
        )
        assert sport.name == "Kabaddi"
        assert str(sport.met_value) == "6.50"
        assert sport.icon == "🤼"

    def test_refuses_when_the_name_already_exists(self, admin):
        proposal = SportProposalFactory(name="Football")
        with pytest.raises(ValidationError) as exc:
            approve_sport_proposal(proposal=proposal, reviewer=admin)
        assert "merge" in exc.value.message_dict["name"][0]

    def test_refuses_a_proposal_that_is_not_pending(self, admin):
        proposal = SportProposalFactory(name="Kabaddi")
        approve_sport_proposal(proposal=proposal, reviewer=admin)
        with pytest.raises(ValidationError) as exc:
            approve_sport_proposal(proposal=proposal, reviewer=admin)
        assert "status" in exc.value.message_dict

    def test_slug_collisions_get_a_suffix(self, admin):
        """Two differently-named sports can slugify the same; the second must not 500."""
        Sport.objects.create(name="Kabaddi Classic", slug="kabaddi")
        proposal = SportProposalFactory(name="Kabaddi")
        sport = approve_sport_proposal(proposal=proposal, reviewer=admin)
        assert sport.slug == "kabaddi-2"


class TestMerge:
    def test_points_the_proposal_at_an_existing_sport(self, admin):
        football = Sport.objects.get(slug="football")
        proposal = SportProposalFactory(name="Soccer")

        merge_sport_proposal(proposal=proposal, reviewer=admin, sport=football, note="Same game.")

        proposal.refresh_from_db()
        assert proposal.status == SportProposal.Status.MERGED
        assert proposal.merged_into == football
        assert proposal.review_note == "Same game."
        assert not proposal.is_open

    def test_creates_no_new_sport(self, admin):
        before = Sport.objects.count()
        merge_sport_proposal(
            proposal=SportProposalFactory(name="Soccer"),
            reviewer=admin,
            sport=Sport.objects.get(slug="football"),
        )
        assert Sport.objects.count() == before

    def test_refuses_a_closed_proposal(self, admin):
        football = Sport.objects.get(slug="football")
        proposal = SportProposalFactory(name="Soccer")
        merge_sport_proposal(proposal=proposal, reviewer=admin, sport=football)
        with pytest.raises(ValidationError):
            merge_sport_proposal(proposal=proposal, reviewer=admin, sport=football)


class TestReject:
    def test_records_the_reason(self, admin):
        proposal = SportProposalFactory()
        reject_sport_proposal(proposal=proposal, reviewer=admin, note="Needs a dedicated court.")
        proposal.refresh_from_db()
        assert proposal.status == SportProposal.Status.REJECTED
        assert proposal.review_note == "Needs a dedicated court."

    def test_requires_a_reason(self, admin):
        with pytest.raises(ValidationError) as exc:
            reject_sport_proposal(proposal=SportProposalFactory(), reviewer=admin, note="  ")
        assert "review_note" in exc.value.message_dict

    def test_refuses_a_closed_proposal(self, admin):
        proposal = SportProposalFactory()
        reject_sport_proposal(proposal=proposal, reviewer=admin, note="No.")
        with pytest.raises(ValidationError):
            reject_sport_proposal(proposal=proposal, reviewer=admin, note="Still no.")


def test_unique_sport_slug_walks_past_collisions():
    Sport.objects.create(name="A", slug="kabaddi")
    Sport.objects.create(name="B", slug="kabaddi-2")
    assert unique_sport_slug("Kabaddi") == "kabaddi-3"


def test_unique_sport_slug_falls_back_for_unsluggable_names():
    assert unique_sport_slug("!!!") == "sport"
