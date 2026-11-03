"""Scoring endpoints, including the public shareable scorecard."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.players.services import get_or_create_profile
from apps.scoring.hooks import (
    clear_scorecard_locked_hooks,
    restore_scorecard_locked_hooks,
)
from apps.scoring.models import TeamSide
from apps.scoring.services import (
    cast_motm_vote,
    close_motm_voting,
    get_or_create_scorecard,
)
from apps.turfs.models import TurfMembership
from apps.turfs.tests.factories import TurfMembershipFactory

from .factories import played_match, ready_to_score, split_teams

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_locked_hooks():
    """Score cards here without the rating engine running behind them."""
    previous = clear_scorecard_locked_hooks()
    yield
    restore_scorecard_locked_hooks(previous)


@pytest.fixture
def client():
    return APIClient()


def roster(match):
    return [entry.player for entry in match.players.order_by("created_at")]


def goals(match, teams, *, a: int, b: int) -> dict:
    stats = {}
    for side, count in ((TeamSide.A, a), (TeamSide.B, b)):
        first = teams[side].players.first()
        if first is not None and count:
            stats[str(first.match_player.player_id)] = {"goals": count}
    return stats


class TestTeamsApi:
    def test_teams_are_created_on_first_read(self, client):
        match = played_match(players=4)
        client.force_authenticate(match.organiser)

        response = client.get(f"/api/v1/matches/{match.id}/teams")
        assert response.status_code == 200
        assert [team["side"] for team in response.data] == ["A", "B"]

    def test_setting_teams(self, client):
        match = played_match(players=4)
        client.force_authenticate(match.organiser)
        entries = list(match.players.order_by("created_at"))

        response = client.post(
            f"/api/v1/matches/{match.id}/teams",
            {
                "assignments": {
                    str(entries[0].id): "A",
                    str(entries[1].id): "A",
                    str(entries[2].id): "B",
                    str(entries[3].id): "B",
                }
            },
            format="json",
        )
        assert response.status_code == 200
        assert len(response.data[0]["players"]) == 2

    def test_a_bystander_cannot_set_teams(self, client):
        match = played_match(players=2)
        client.force_authenticate(UserFactory())
        response = client.post(
            f"/api/v1/matches/{match.id}/teams", {"assignments": {}}, format="json"
        )
        # Not on the roster and not on the board: the match is simply not theirs to see.
        assert response.status_code in (400, 404)

    def test_auto_balance(self, client):
        match = played_match(players=6)
        client.force_authenticate(match.organiser)

        response = client.post(f"/api/v1/matches/{match.id}/teams/auto-balance")
        assert response.status_code == 200
        assert sum(len(team["players"]) for team in response.data) == 6

    def test_naming_a_captain(self, client):
        match = played_match(players=4)
        teams = split_teams(match, captains=False)
        player = teams[TeamSide.A].players.first().player
        profile = get_or_create_profile(player)
        client.force_authenticate(match.organiser)

        response = client.post(
            f"/api/v1/matches/{match.id}/teams/captain",
            {"side": "A", "player_id": str(profile.id)},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["captain_name"]


class TestScorecardApi:
    def test_it_is_created_in_draft_on_first_read(self, client):
        match = played_match(players=4)
        client.force_authenticate(match.organiser)

        response = client.get(f"/api/v1/matches/{match.id}/scorecard")
        assert response.status_code == 200
        assert response.data["status"] == "draft"
        assert response.data["can_edit"] is True

    def test_the_form_is_generated_from_the_sport(self, client):
        """The entry screen renders from these, so a new stat needs no frontend change."""
        match = played_match(players=4, sport="cricket", fmt="box")
        client.force_authenticate(match.organiser)

        keys = {
            definition["key"]
            for definition in client.get(f"/api/v1/matches/{match.id}/scorecard").data[
                "stat_definitions"
            ]
        }
        assert {"runs", "balls", "wickets", "overs"} <= keys

    def test_saving_a_draft(self, client):
        match, teams, _ = ready_to_score(players=4)
        client.force_authenticate(match.organiser)

        response = client.patch(
            f"/api/v1/matches/{match.id}/scorecard",
            {"team_a_score": 3, "team_b_score": 1, "stats": goals(match, teams, a=3, b=1)},
            format="json",
        )
        assert response.status_code == 200
        assert response.data["team_a_score"] == 3
        assert len(response.data["rows"]) == 2

    def test_submitting_and_confirming_locks_it(self, client):
        """Acceptance, over HTTP: submit, the other captain confirms, it locks."""
        match, teams, _ = ready_to_score(players=4)
        client.force_authenticate(match.organiser)
        client.patch(
            f"/api/v1/matches/{match.id}/scorecard",
            {"team_a_score": 5, "team_b_score": 3, "stats": goals(match, teams, a=5, b=3)},
            format="json",
        )
        submitted = client.post(f"/api/v1/matches/{match.id}/scorecard/submit")
        assert submitted.status_code == 200
        assert submitted.data["status"] == "submitted"

        client.force_authenticate(teams[TeamSide.B].captain)
        confirmed = client.post(f"/api/v1/matches/{match.id}/scorecard/confirm")
        assert confirmed.status_code == 200
        assert confirmed.data["status"] == "locked"
        assert confirmed.data["result"] == "A"

    def test_validation_errors_come_back_per_field(self, client):
        """So the entry form can show each message against its input."""
        match, teams, _ = ready_to_score(players=4)
        client.force_authenticate(match.organiser)
        client.patch(
            f"/api/v1/matches/{match.id}/scorecard",
            {"team_a_score": 1, "team_b_score": 0, "stats": goals(match, teams, a=5, b=0)},
            format="json",
        )

        response = client.post(f"/api/v1/matches/{match.id}/scorecard/submit")
        assert response.status_code == 400
        assert "goals" in response.data

    def test_the_scorer_cannot_confirm_their_own(self, client):
        match, teams, _ = ready_to_score(players=4)
        client.force_authenticate(match.organiser)
        client.patch(
            f"/api/v1/matches/{match.id}/scorecard",
            {"team_a_score": 1, "team_b_score": 0},
            format="json",
        )
        client.post(f"/api/v1/matches/{match.id}/scorecard/submit")

        response = client.post(f"/api/v1/matches/{match.id}/scorecard/confirm")
        assert response.status_code == 400

    def test_dispute_then_staff_resolve(self, client):
        match, teams, _ = ready_to_score(players=4)
        staff = TurfMembershipFactory(turf=match.turf, role=TurfMembership.Role.CASHIER).user

        client.force_authenticate(match.organiser)
        client.patch(
            f"/api/v1/matches/{match.id}/scorecard",
            {"team_a_score": 3, "team_b_score": 1, "stats": goals(match, teams, a=3, b=1)},
            format="json",
        )
        client.post(f"/api/v1/matches/{match.id}/scorecard/submit")

        client.force_authenticate(teams[TeamSide.B].captain)
        disputed = client.post(
            f"/api/v1/matches/{match.id}/scorecard/dispute",
            {"reason": "It was 2–1"},
            format="json",
        )
        assert disputed.data["status"] == "disputed"

        client.force_authenticate(staff)
        resolved = client.post(
            f"/api/v1/matches/{match.id}/scorecard/resolve",
            {"team_a_score": 2, "team_b_score": 1, "stats": goals(match, teams, a=2, b=1)},
            format="json",
        )
        assert resolved.status_code == 200
        assert resolved.data["status"] == "locked"
        assert resolved.data["verified_by_staff"] is True
        assert resolved.data["team_a_score"] == 2

    def test_can_confirm_tells_the_ui_who_may_act(self, client):
        match, teams, _ = ready_to_score(players=4)
        client.force_authenticate(match.organiser)
        client.patch(
            f"/api/v1/matches/{match.id}/scorecard",
            {"team_a_score": 1, "team_b_score": 0},
            format="json",
        )
        client.post(f"/api/v1/matches/{match.id}/scorecard/submit")

        assert client.get(f"/api/v1/matches/{match.id}/scorecard").data["can_confirm"] is False

        client.force_authenticate(teams[TeamSide.B].captain)
        assert client.get(f"/api/v1/matches/{match.id}/scorecard").data["can_confirm"] is True


def submit_and_lock(client, match, teams) -> None:
    client.force_authenticate(match.organiser)
    client.patch(
        f"/api/v1/matches/{match.id}/scorecard",
        {"team_a_score": 3, "team_b_score": 1, "stats": goals(match, teams, a=3, b=1)},
        format="json",
    )
    client.post(f"/api/v1/matches/{match.id}/scorecard/submit")
    client.force_authenticate(teams[TeamSide.B].captain)
    client.post(f"/api/v1/matches/{match.id}/scorecard/confirm")


class TestPublicScorecard:
    def test_it_opens_without_signing_in(self, client):
        """Acceptance: the public link opens without sign-in."""
        match, teams, _ = ready_to_score(players=4)
        submit_and_lock(client, match, teams)

        anonymous = APIClient()
        response = anonymous.get(f"/api/v1/public/matches/{match.id}/scorecard")
        assert response.status_code == 200
        assert response.data["team_a_score"] == 3
        assert response.data["turf_name"]
        assert len(response.data["teams"]) == 2

    def test_an_unlocked_scorecard_is_not_public(self, client):
        """A link shared before the result is settled would be shared before it is true."""
        match, teams, _ = ready_to_score(players=4)
        client.force_authenticate(match.organiser)
        client.patch(
            f"/api/v1/matches/{match.id}/scorecard",
            {"team_a_score": 1, "team_b_score": 0},
            format="json",
        )
        client.post(f"/api/v1/matches/{match.id}/scorecard/submit")

        anonymous = APIClient()
        assert anonymous.get(f"/api/v1/public/matches/{match.id}/scorecard").status_code == 404

    def test_it_hides_reader_specific_fields(self, client):
        match, teams, _ = ready_to_score(players=4)
        submit_and_lock(client, match, teams)

        data = APIClient().get(f"/api/v1/public/matches/{match.id}/scorecard").data
        for hidden in ("can_edit", "can_confirm", "my_motm_vote", "events", "dispute_reason"):
            assert hidden not in data


class TestMotmAndRatings:
    def test_voting_over_http(self, client):
        match, teams, _ = ready_to_score(players=4)
        client.force_authenticate(match.organiser)
        client.patch(
            f"/api/v1/matches/{match.id}/scorecard",
            {"team_a_score": 1, "team_b_score": 0},
            format="json",
        )
        client.post(f"/api/v1/matches/{match.id}/scorecard/submit")

        players = roster(match)
        nominee = get_or_create_profile(players[1])
        client.force_authenticate(players[0])

        response = client.post(
            f"/api/v1/matches/{match.id}/motm",
            {"player_id": str(nominee.id)},
            format="json",
        )
        assert response.status_code == 200
        assert str(response.data["my_motm_vote"]) == str(nominee.id)

    def test_voting_for_yourself_is_refused(self, client):
        match, teams, _ = ready_to_score(players=4)
        client.force_authenticate(match.organiser)
        client.patch(f"/api/v1/matches/{match.id}/scorecard", {"team_a_score": 1}, format="json")
        client.post(f"/api/v1/matches/{match.id}/scorecard/submit")

        me = get_or_create_profile(match.organiser)
        response = client.post(
            f"/api/v1/matches/{match.id}/motm", {"player_id": str(me.id)}, format="json"
        )
        assert response.status_code == 400

    def test_the_award_shows_on_the_public_card(self, client):
        match, teams, _ = ready_to_score(players=4)
        players = roster(match)
        client.force_authenticate(match.organiser)
        client.patch(
            f"/api/v1/matches/{match.id}/scorecard",
            {"team_a_score": 3, "team_b_score": 1, "stats": goals(match, teams, a=3, b=1)},
            format="json",
        )
        client.post(f"/api/v1/matches/{match.id}/scorecard/submit")

        cast_motm_vote(match=match, voter=players[1], nominee=players[0])
        scorecard = get_or_create_scorecard(match=match)
        close_motm_voting(scorecard=scorecard)

        client.force_authenticate(teams[TeamSide.B].captain)
        client.post(f"/api/v1/matches/{match.id}/scorecard/confirm")

        data = APIClient().get(f"/api/v1/public/matches/{match.id}/scorecard").data
        assert data["motm_name"]

    def test_peer_ratings(self, client):
        match, teams, _ = ready_to_score(players=4)
        client.force_authenticate(match.organiser)
        client.patch(f"/api/v1/matches/{match.id}/scorecard", {"team_a_score": 1}, format="json")
        client.post(f"/api/v1/matches/{match.id}/scorecard/submit")

        players = roster(match)
        client.force_authenticate(players[0])
        response = client.post(
            f"/api/v1/matches/{match.id}/peer-ratings",
            {
                "ratings": [
                    {
                        "player_id": str(get_or_create_profile(players[1]).id),
                        "overall": 4,
                        "skill_taps": ["passing"],
                    }
                ]
            },
            format="json",
        )
        assert response.status_code == 200
        assert response.data["saved"] == 1

    def test_rating_yourself_is_refused(self, client):
        match, teams, _ = ready_to_score(players=4)
        client.force_authenticate(match.organiser)
        client.patch(f"/api/v1/matches/{match.id}/scorecard", {"team_a_score": 1}, format="json")
        client.post(f"/api/v1/matches/{match.id}/scorecard/submit")

        me = get_or_create_profile(match.organiser)
        response = client.post(
            f"/api/v1/matches/{match.id}/peer-ratings",
            {"ratings": [{"player_id": str(me.id), "overall": 5}]},
            format="json",
        )
        assert response.status_code == 400


def test_player_results_report_the_outcome_from_their_side(client):
    match, teams, _ = ready_to_score(players=4)
    submit_and_lock(client, match, teams)

    winner = teams[TeamSide.A].players.first().player
    loser = teams[TeamSide.B].players.first().player

    client.force_authenticate(winner)
    won = client.get(f"/api/v1/players/{get_or_create_profile(winner).id}/results").data
    assert won[0]["outcome"] == "win"

    lost = client.get(f"/api/v1/players/{get_or_create_profile(loser).id}/results").data
    assert lost[0]["outcome"] == "loss"


def test_an_unlocked_match_is_not_in_the_results(client):
    match, teams, _ = ready_to_score(players=4)
    player = teams[TeamSide.A].players.first().player
    client.force_authenticate(player)

    results = client.get(f"/api/v1/players/{get_or_create_profile(player).id}/results").data
    assert results == []
