"""Teams, the scorecard state machine, MOTM and peer ratings (DOMAIN §7)."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError

from apps.accounts.tests.factories import UserFactory
from apps.core.utils import now
from apps.matches.models import MatchStatus
from apps.notifications.models import Notification, NotificationKind
from apps.scoring.hooks import clear_scorecard_locked_hooks, register_scorecard_locked_hook
from apps.scoring.models import (
    MatchResult,
    MatchTeamPlayer,
    MotmVote,
    PeerRating,
    PlayerStat,
    Scorecard,
    ScorecardStatus,
    TeamSide,
)
from apps.scoring.services import (
    assign_scorer,
    auto_balance_teams,
    auto_confirm_submitted_scorecards,
    can_confirm,
    cast_motm_vote,
    close_finished_motm_voting,
    close_motm_voting,
    confirm_scorecard,
    dispute_scorecard,
    get_or_create_scorecard,
    lock_scorecard,
    player_rating,
    resolve_dispute,
    save_draft,
    set_captain,
    set_teams,
    submit_peer_ratings,
    submit_scorecard,
)
from apps.turfs.models import TurfMembership
from apps.turfs.tests.factories import TurfMembershipFactory

from .factories import onboard, played_match, ready_to_score, split_teams

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_locked_hooks():
    """Phase 06 registers one; these tests opt in explicitly."""
    clear_scorecard_locked_hooks()
    yield
    clear_scorecard_locked_hooks()


def roster(match):
    return [entry.player for entry in match.players.order_by("created_at")]


def goals_for(match, teams, *, a: int, b: int) -> dict:
    """Give team A's first player ``a`` goals and team B's first ``b``."""
    stats = {}
    for side, count in ((TeamSide.A, a), (TeamSide.B, b)):
        first = teams[side].players.first()
        if first is not None and count:
            stats[str(first.match_player.player_id)] = {"goals": count}
    return stats


class TestTeams:
    def test_set_teams_splits_the_roster(self):
        match = played_match(players=4)
        teams = split_teams(match, captains=False)

        assert teams[TeamSide.A].players.count() == 2
        assert teams[TeamSide.B].players.count() == 2

    def test_setting_teams_again_replaces_the_sheet(self):
        match = played_match(players=4)
        split_teams(match, captains=False)
        split_teams(match, captains=False)

        assert MatchTeamPlayer.objects.filter(team__match=match).count() == 4

    def test_only_the_organiser_or_staff_can_set_teams(self):
        match = played_match(players=2)
        with pytest.raises(ValidationError) as exc:
            set_teams(match=match, assignments={}, actor=UserFactory())
        assert "match" in exc.value.message_dict

    def test_turf_staff_can_set_teams(self):
        match = played_match(players=2)
        staff = TurfMembershipFactory(turf=match.turf, role=TurfMembership.Role.CASHIER).user
        assert set_teams(match=match, assignments={}, actor=staff)

    def test_a_player_not_on_the_roster_cannot_be_assigned(self):
        match = played_match(players=2)
        with pytest.raises(ValidationError) as exc:
            set_teams(
                match=match,
                assignments={"00000000-0000-0000-0000-000000000000": TeamSide.A},
                actor=match.organiser,
            )
        assert "assignments" in exc.value.message_dict

    def test_an_unknown_side_is_refused(self):
        match = played_match(players=2)
        entry = match.players.first()
        with pytest.raises(ValidationError):
            set_teams(match=match, assignments={str(entry.id): "C"}, actor=match.organiser)

    def test_the_captain_must_be_on_that_team(self):
        match = played_match(players=4)
        teams = split_teams(match, captains=False)
        outsider = teams[TeamSide.B].players.first().player

        with pytest.raises(ValidationError) as exc:
            set_captain(match=match, side=TeamSide.A, player=outsider, actor=match.organiser)
        assert "player" in exc.value.message_dict


class TestAutoBalance:
    def test_it_splits_evenly(self):
        match = played_match(players=6)
        for player in roster(match):
            onboard(player)

        teams = {team.side: team for team in auto_balance_teams(match=match, actor=match.organiser)}
        assert teams[TeamSide.A].players.count() == 3
        assert teams[TeamSide.B].players.count() == 3

    def test_it_keeps_the_sides_close_in_strength(self):
        """The whole point: two sides a player would call fair."""
        match = played_match(players=6)
        for index, player in enumerate(roster(match)):
            onboard(player, skill=30 + index * 10)

        teams = {team.side: team for team in auto_balance_teams(match=match, actor=match.organiser)}
        totals = {
            side: sum(player_rating(match, entry.player) for entry in team.players.all())
            for side, team in teams.items()
        }
        # Greedy on a descending sort keeps the gap inside one player's rating.
        assert abs(totals[TeamSide.A] - totals[TeamSide.B]) <= 25

    def test_an_odd_roster_differs_by_one(self):
        match = played_match(players=5)
        teams = {team.side: team for team in auto_balance_teams(match=match, actor=match.organiser)}
        counts = sorted(team.players.count() for team in teams.values())
        assert counts == [2, 3]

    def test_an_empty_roster_is_refused(self):
        match = played_match(players=1)
        match.players.all().delete()
        with pytest.raises(ValidationError):
            auto_balance_teams(match=match, actor=match.organiser)

    def test_unrated_players_are_treated_as_mid_range(self):
        """A match of brand-new players must still split, not crash."""
        match = played_match(players=4)
        teams = {team.side: team for team in auto_balance_teams(match=match, actor=match.organiser)}
        assert teams[TeamSide.A].players.count() == 2


class TestScorer:
    def test_the_organiser_scores_by_default(self):
        match = played_match(players=2)
        assert get_or_create_scorecard(match=match).scorer == match.organiser

    def test_it_is_idempotent(self):
        match = played_match(players=2)
        first = get_or_create_scorecard(match=match)
        assert get_or_create_scorecard(match=match).pk == first.pk

    def test_scoring_can_be_handed_to_a_captain(self):
        match, teams, scorecard = ready_to_score()
        captain = teams[TeamSide.B].captain

        assign_scorer(scorecard=scorecard, actor=match.organiser, scorer=captain)
        assert scorecard.scorer == captain

    def test_scoring_cannot_be_handed_to_a_bystander(self):
        match, _, scorecard = ready_to_score()
        with pytest.raises(ValidationError) as exc:
            assign_scorer(scorecard=scorecard, actor=match.organiser, scorer=UserFactory())
        assert "scorer" in exc.value.message_dict


class TestSubmit:
    def test_the_happy_path(self):
        """Acceptance: scorer submits 5–3 with goals that add up."""
        match, teams, scorecard = ready_to_score(players=4)
        save_draft(
            scorecard=scorecard,
            actor=match.organiser,
            team_a_score=5,
            team_b_score=3,
            stats=goals_for(match, teams, a=5, b=3),
        )

        submit_scorecard(scorecard=scorecard, actor=match.organiser)

        scorecard.refresh_from_db()
        assert scorecard.status == ScorecardStatus.SUBMITTED
        assert scorecard.result == MatchResult.TEAM_A
        assert scorecard.submitted_at is not None

    def test_goals_exceeding_the_team_score_are_rejected(self):
        """Acceptance: goals that exceed the team score are rejected."""
        match, teams, scorecard = ready_to_score(players=4)
        save_draft(
            scorecard=scorecard,
            actor=match.organiser,
            team_a_score=2,
            team_b_score=0,
            stats=goals_for(match, teams, a=5, b=0),
        )

        with pytest.raises(ValidationError) as exc:
            submit_scorecard(scorecard=scorecard, actor=match.organiser)
        assert "goals" in exc.value.message_dict

        scorecard.refresh_from_db()
        assert scorecard.status == ScorecardStatus.DRAFT

    def test_a_draft_is_not_validated(self):
        """A scorer filling in a phone form must not be blocked halfway through."""
        match, teams, scorecard = ready_to_score(players=4)
        save_draft(
            scorecard=scorecard,
            actor=match.organiser,
            team_a_score=1,
            stats=goals_for(match, teams, a=9, b=0),
        )
        assert scorecard.status == ScorecardStatus.DRAFT

    def test_submitting_without_teams_is_refused(self):
        match = played_match(players=4)
        scorecard = get_or_create_scorecard(match=match)
        with pytest.raises(ValidationError) as exc:
            submit_scorecard(scorecard=scorecard, actor=match.organiser)
        assert "teams" in exc.value.message_dict

    def test_a_bystander_cannot_score(self):
        _, _, scorecard = ready_to_score()
        with pytest.raises(ValidationError):
            save_draft(scorecard=scorecard, actor=UserFactory(), team_a_score=1)

    def test_stats_for_a_player_not_on_the_roster_are_refused(self):
        match, _, scorecard = ready_to_score()
        stranger = UserFactory()
        with pytest.raises(ValidationError) as exc:
            save_draft(
                scorecard=scorecard,
                actor=match.organiser,
                stats={str(stranger.id): {"goals": 1}},
            )
        assert "stats" in exc.value.message_dict

    def test_a_stat_the_sport_does_not_define_is_refused(self):
        match, _, scorecard = ready_to_score()
        player = roster(match)[0]
        with pytest.raises(ValidationError):
            save_draft(
                scorecard=scorecard,
                actor=match.organiser,
                stats={str(player.id): {"wickets": 3}},
            )

    def test_submitting_twice_is_refused(self):
        match, teams, scorecard = ready_to_score()
        save_draft(scorecard=scorecard, actor=match.organiser, team_a_score=1, team_b_score=0)
        submit_scorecard(scorecard=scorecard, actor=match.organiser)
        with pytest.raises(ValidationError):
            submit_scorecard(scorecard=scorecard, actor=match.organiser)

    def test_a_staff_entered_card_is_verified_from_the_outset(self):
        """DECISIONS D7."""
        match, teams, scorecard = ready_to_score()
        staff = TurfMembershipFactory(turf=match.turf, role=TurfMembership.Role.CASHIER).user
        save_draft(scorecard=scorecard, actor=staff, team_a_score=2, team_b_score=1)
        submit_scorecard(scorecard=scorecard, actor=staff)

        scorecard.refresh_from_db()
        assert scorecard.verified_by_staff is True

    def test_submitting_marks_attendance(self):
        match, teams, scorecard = ready_to_score(players=4)
        save_draft(scorecard=scorecard, actor=match.organiser, team_a_score=1, team_b_score=0)
        submit_scorecard(scorecard=scorecard, actor=match.organiser)

        assert match.players.filter(attended=True).count() == 4

    def test_the_opposing_captain_is_told(self):
        match, teams, scorecard = ready_to_score()
        save_draft(scorecard=scorecard, actor=match.organiser, team_a_score=1, team_b_score=0)
        submit_scorecard(scorecard=scorecard, actor=match.organiser)

        assert Notification.objects.filter(kind=NotificationKind.SCORECARD_SUBMITTED).exists()


def submitted(players: int = 4):
    """A submitted scorecard, ready to be confirmed or disputed."""
    match, teams, scorecard = ready_to_score(players=players)
    save_draft(
        scorecard=scorecard,
        actor=match.organiser,
        team_a_score=3,
        team_b_score=1,
        stats=goals_for(match, teams, a=3, b=1),
    )
    submit_scorecard(scorecard=scorecard, actor=match.organiser)
    scorecard.refresh_from_db()
    return match, teams, scorecard


class TestConfirm:
    def test_the_opposing_captain_confirms_and_it_locks(self):
        """Acceptance: the other captain confirms, the scorecard locks."""
        match, teams, scorecard = submitted()
        opposing = teams[TeamSide.B].captain

        confirm_scorecard(scorecard=scorecard, actor=opposing)

        scorecard.refresh_from_db()
        assert scorecard.status == ScorecardStatus.LOCKED
        assert scorecard.confirmed_by == opposing
        assert scorecard.locked_at is not None

    def test_the_scorer_cannot_confirm_their_own_card(self):
        match, _, scorecard = submitted()
        assert can_confirm(scorecard=scorecard, user=match.organiser) is False
        with pytest.raises(ValidationError):
            confirm_scorecard(scorecard=scorecard, actor=match.organiser)

    def test_their_own_captain_cannot_confirm(self):
        match, teams, scorecard = submitted()
        # The scorer is on team A, so team A's captain is not "opposing".
        own = teams[TeamSide.A].captain
        if own and own.id != match.organiser.id:
            assert can_confirm(scorecard=scorecard, user=own) is False

    def test_a_bystander_cannot_confirm(self):
        _, _, scorecard = submitted()
        with pytest.raises(ValidationError):
            confirm_scorecard(scorecard=scorecard, actor=UserFactory())

    def test_turf_staff_can_confirm_and_that_verifies_it(self):
        match, _, scorecard = submitted()
        staff = TurfMembershipFactory(turf=match.turf, role=TurfMembership.Role.CASHIER).user

        confirm_scorecard(scorecard=scorecard, actor=staff)

        scorecard.refresh_from_db()
        assert scorecard.verified_by_staff is True
        assert scorecard.status == ScorecardStatus.LOCKED

    def test_locking_marks_the_match_finished(self):
        match, teams, scorecard = submitted()
        confirm_scorecard(scorecard=scorecard, actor=teams[TeamSide.B].captain)
        match.refresh_from_db()
        assert match.status == MatchStatus.FINISHED

    def test_locking_fires_the_phase_06_hook(self):
        seen = []
        register_scorecard_locked_hook(lambda scorecard, **_: seen.append(scorecard.id))

        match, teams, scorecard = submitted()
        confirm_scorecard(scorecard=scorecard, actor=teams[TeamSide.B].captain)

        assert seen == [scorecard.id]

    def test_a_failing_hook_does_not_undo_the_lock(self):
        """A rating engine that cannot run is a separate problem to fix."""

        def boom(**_):
            raise RuntimeError("engine down")

        register_scorecard_locked_hook(boom)

        match, teams, scorecard = submitted()
        confirm_scorecard(scorecard=scorecard, actor=teams[TeamSide.B].captain)

        scorecard.refresh_from_db()
        assert scorecard.status == ScorecardStatus.LOCKED

    def test_a_locked_card_cannot_be_edited(self):
        match, teams, scorecard = submitted()
        confirm_scorecard(scorecard=scorecard, actor=teams[TeamSide.B].captain)
        scorecard.refresh_from_db()

        with pytest.raises(ValidationError):
            save_draft(scorecard=scorecard, actor=match.organiser, team_a_score=9)

    def test_a_locked_card_cannot_be_locked_again(self):
        match, teams, scorecard = submitted()
        confirm_scorecard(scorecard=scorecard, actor=teams[TeamSide.B].captain)
        scorecard.refresh_from_db()
        with pytest.raises(ValidationError):
            lock_scorecard(scorecard=scorecard)

    def test_everyone_is_told_the_result(self):
        match, teams, scorecard = submitted()
        confirm_scorecard(scorecard=scorecard, actor=teams[TeamSide.B].captain)
        assert Notification.objects.filter(kind=NotificationKind.SCORECARD_LOCKED).count() == 4


class TestDispute:
    def test_dispute_then_staff_resolve_locks_it_verified(self):
        """Acceptance: dispute → staff resolves → locked, marked verified."""
        match, teams, scorecard = submitted()
        staff = TurfMembershipFactory(turf=match.turf, role=TurfMembership.Role.CASHIER).user

        dispute_scorecard(
            scorecard=scorecard, actor=teams[TeamSide.B].captain, reason="It was 2–1, not 3–1"
        )
        scorecard.refresh_from_db()
        assert scorecard.status == ScorecardStatus.DISPUTED

        resolve_dispute(
            scorecard=scorecard,
            actor=staff,
            team_a_score=2,
            team_b_score=1,
            stats=goals_for(match, teams, a=2, b=1),
        )

        scorecard.refresh_from_db()
        assert scorecard.status == ScorecardStatus.LOCKED
        assert scorecard.verified_by_staff is True
        assert scorecard.team_a_score == 2
        assert scorecard.resolved_by == staff

    def test_a_dispute_needs_a_reason(self):
        _, teams, scorecard = submitted()
        with pytest.raises(ValidationError) as exc:
            dispute_scorecard(scorecard=scorecard, actor=teams[TeamSide.B].captain, reason="  ")
        assert "reason" in exc.value.message_dict

    def test_only_the_confirming_side_can_dispute(self):
        _, _, scorecard = submitted()
        with pytest.raises(ValidationError):
            dispute_scorecard(scorecard=scorecard, actor=UserFactory(), reason="Wrong")

    def test_a_player_cannot_resolve_their_own_dispute(self):
        match, teams, scorecard = submitted()
        dispute_scorecard(scorecard=scorecard, actor=teams[TeamSide.B].captain, reason="Wrong")
        with pytest.raises(ValidationError) as exc:
            resolve_dispute(scorecard=scorecard, actor=teams[TeamSide.B].captain)
        assert "actor" in exc.value.message_dict

    def test_a_platform_admin_can_resolve(self):
        from apps.accounts.tests.factories import PlatformAdminFactory

        match, teams, scorecard = submitted()
        dispute_scorecard(scorecard=scorecard, actor=teams[TeamSide.B].captain, reason="Wrong")

        resolve_dispute(scorecard=scorecard, actor=PlatformAdminFactory())
        scorecard.refresh_from_db()
        assert scorecard.status == ScorecardStatus.LOCKED

    def test_a_resolution_still_has_to_add_up(self):
        match, teams, scorecard = submitted()
        staff = TurfMembershipFactory(turf=match.turf, role=TurfMembership.Role.CASHIER).user
        dispute_scorecard(scorecard=scorecard, actor=teams[TeamSide.B].captain, reason="Wrong")

        with pytest.raises(ValidationError) as exc:
            resolve_dispute(
                scorecard=scorecard,
                actor=staff,
                team_a_score=1,
                team_b_score=0,
                stats=goals_for(match, teams, a=5, b=0),
            )
        assert "goals" in exc.value.message_dict

    def test_a_disputed_card_can_be_corrected_and_resubmitted_by_the_scorer(self):
        match, teams, scorecard = submitted()
        dispute_scorecard(scorecard=scorecard, actor=teams[TeamSide.B].captain, reason="Wrong")

        save_draft(
            scorecard=scorecard,
            actor=match.organiser,
            team_a_score=2,
            team_b_score=1,
            stats=goals_for(match, teams, a=2, b=1),
        )
        submit_scorecard(scorecard=scorecard, actor=match.organiser)

        scorecard.refresh_from_db()
        assert scorecard.status == ScorecardStatus.SUBMITTED
        assert scorecard.dispute_reason == ""


class TestAutoConfirm:
    def test_silence_for_the_window_counts_as_agreement(self):
        _, _, scorecard = submitted()
        Scorecard.objects.filter(pk=scorecard.pk).update(
            submitted_at=now() - timedelta(hours=settings.SCORECARD_AUTO_CONFIRM_HOURS + 1)
        )

        assert auto_confirm_submitted_scorecards() == 1

        scorecard.refresh_from_db()
        assert scorecard.status == ScorecardStatus.LOCKED
        assert scorecard.auto_confirmed is True

    def test_a_fresh_submission_is_left_alone(self):
        _, _, scorecard = submitted()
        assert auto_confirm_submitted_scorecards() == 0
        scorecard.refresh_from_db()
        assert scorecard.status == ScorecardStatus.SUBMITTED

    def test_a_disputed_card_is_not_auto_confirmed(self):
        """Somebody has objected; the clock must not override them."""
        _, teams, scorecard = submitted()
        dispute_scorecard(scorecard=scorecard, actor=teams[TeamSide.B].captain, reason="Wrong")
        Scorecard.objects.filter(pk=scorecard.pk).update(
            submitted_at=now() - timedelta(hours=settings.SCORECARD_AUTO_CONFIRM_HOURS + 1)
        )

        assert auto_confirm_submitted_scorecards() == 0


class TestMotm:
    def test_a_clear_winner(self):
        match, teams, scorecard = submitted()
        players = roster(match)

        cast_motm_vote(match=match, voter=players[1], nominee=players[0])
        cast_motm_vote(match=match, voter=players[2], nominee=players[0])
        cast_motm_vote(match=match, voter=players[3], nominee=players[1])

        close_motm_voting(scorecard=scorecard)
        scorecard.refresh_from_db()
        assert scorecard.motm == players[0]

    def test_nobody_can_vote_for_themselves(self):
        match, _, scorecard = submitted()
        player = roster(match)[0]
        with pytest.raises(ValidationError) as exc:
            cast_motm_vote(match=match, voter=player, nominee=player)
        assert "nominee" in exc.value.message_dict

    def test_only_players_in_the_match_can_vote(self):
        match, _, _ = submitted()
        with pytest.raises(ValidationError) as exc:
            cast_motm_vote(match=match, voter=UserFactory(), nominee=roster(match)[0])
        assert "voter" in exc.value.message_dict

    def test_you_can_only_vote_for_somebody_who_played(self):
        match, _, _ = submitted()
        with pytest.raises(ValidationError) as exc:
            cast_motm_vote(match=match, voter=roster(match)[0], nominee=UserFactory())
        assert "nominee" in exc.value.message_dict

    def test_changing_your_vote_replaces_it(self):
        match, _, _ = submitted()
        players = roster(match)
        cast_motm_vote(match=match, voter=players[0], nominee=players[1])
        cast_motm_vote(match=match, voter=players[0], nominee=players[2])

        assert MotmVote.objects.filter(match=match, voter=players[0]).count() == 1
        assert MotmVote.objects.get(match=match, voter=players[0]).nominee == players[2]

    def test_voting_is_closed_before_submission(self):
        match, _, scorecard = ready_to_score()
        with pytest.raises(ValidationError):
            cast_motm_vote(match=match, voter=roster(match)[0], nominee=roster(match)[1])

    def test_voting_closes_after_the_window(self):
        match, _, scorecard = submitted()
        Scorecard.objects.filter(pk=scorecard.pk).update(
            submitted_at=now() - timedelta(hours=settings.MOTM_VOTE_WINDOW_HOURS + 1)
        )
        scorecard.refresh_from_db()

        with pytest.raises(ValidationError) as exc:
            cast_motm_vote(match=match, voter=roster(match)[0], nominee=roster(match)[1])
        assert "closed" in exc.value.message_dict["match"][0]

    def test_a_tie_is_broken_on_stat_contribution(self):
        """DOMAIN §7: tie → higher stat contribution."""
        match, teams, scorecard = ready_to_score(players=4)
        players = roster(match)
        save_draft(
            scorecard=scorecard,
            actor=match.organiser,
            team_a_score=3,
            team_b_score=1,
            stats={
                str(players[0].id): {"goals": 3},
                str(players[1].id): {"goals": 1},
            },
        )
        submit_scorecard(scorecard=scorecard, actor=match.organiser)
        scorecard.refresh_from_db()

        # One vote each: a dead heat on votes.
        cast_motm_vote(match=match, voter=players[2], nominee=players[0])
        cast_motm_vote(match=match, voter=players[3], nominee=players[1])

        close_motm_voting(scorecard=scorecard)
        scorecard.refresh_from_db()
        assert scorecard.motm == players[0]

    def test_no_votes_means_no_award(self):
        _, _, scorecard = submitted()
        close_motm_voting(scorecard=scorecard)
        scorecard.refresh_from_db()
        assert scorecard.motm is None
        assert scorecard.motm_closed_at is not None

    def test_closing_twice_changes_nothing(self):
        match, _, scorecard = submitted()
        players = roster(match)
        cast_motm_vote(match=match, voter=players[1], nominee=players[0])
        close_motm_voting(scorecard=scorecard)
        first = scorecard.motm_closed_at

        close_motm_voting(scorecard=scorecard)
        scorecard.refresh_from_db()
        assert scorecard.motm_closed_at == first

    def test_the_winner_is_told(self):
        match, _, scorecard = submitted()
        players = roster(match)
        cast_motm_vote(match=match, voter=players[1], nominee=players[0])
        close_motm_voting(scorecard=scorecard)

        assert Notification.objects.filter(
            user=players[0], kind=NotificationKind.MOTM_AWARDED
        ).exists()

    def test_the_scheduled_job_closes_due_votes(self):
        _, _, scorecard = submitted()
        Scorecard.objects.filter(pk=scorecard.pk).update(
            submitted_at=now() - timedelta(hours=settings.MOTM_VOTE_WINDOW_HOURS + 1)
        )
        assert close_finished_motm_voting() == 1


class TestPeerRatings:
    def test_rating_teammates(self):
        match, _, scorecard = submitted()
        players = roster(match)

        saved = submit_peer_ratings(
            match=match,
            rater=players[0],
            ratings=[
                {"player_id": str(players[1].id), "overall": 4, "skill_taps": ["passing"]},
                {"player_id": str(players[2].id), "overall": 5},
            ],
        )
        assert len(saved) == 2
        assert PeerRating.objects.filter(match=match, rater=players[0]).count() == 2

    def test_rating_the_same_player_twice_replaces_it(self):
        match, _, _ = submitted()
        players = roster(match)
        submit_peer_ratings(
            match=match, rater=players[0], ratings=[{"player_id": str(players[1].id), "overall": 2}]
        )
        submit_peer_ratings(
            match=match, rater=players[0], ratings=[{"player_id": str(players[1].id), "overall": 5}]
        )

        rating = PeerRating.objects.get(match=match, rater=players[0], ratee=players[1])
        assert rating.overall == 5

    def test_you_cannot_rate_yourself(self):
        match, _, _ = submitted()
        player = roster(match)[0]
        with pytest.raises(ValidationError):
            submit_peer_ratings(
                match=match, rater=player, ratings=[{"player_id": str(player.id), "overall": 5}]
            )

    def test_you_cannot_rate_somebody_who_did_not_play(self):
        match, _, _ = submitted()
        with pytest.raises(ValidationError):
            submit_peer_ratings(
                match=match,
                rater=roster(match)[0],
                ratings=[{"player_id": str(UserFactory().id), "overall": 5}],
            )

    def test_a_bystander_cannot_rate(self):
        match, _, _ = submitted()
        with pytest.raises(ValidationError):
            submit_peer_ratings(
                match=match,
                rater=UserFactory(),
                ratings=[{"player_id": str(roster(match)[0].id), "overall": 5}],
            )

    def test_a_rating_outside_one_to_five_is_refused(self):
        match, _, _ = submitted()
        players = roster(match)
        with pytest.raises(ValidationError):
            submit_peer_ratings(
                match=match,
                rater=players[0],
                ratings=[{"player_id": str(players[1].id), "overall": 9}],
            )

    def test_rating_before_submission_is_refused(self):
        match, _, _ = ready_to_score()
        players = roster(match)
        with pytest.raises(ValidationError):
            submit_peer_ratings(
                match=match,
                rater=players[0],
                ratings=[{"player_id": str(players[1].id), "overall": 4}],
            )

    def test_the_per_match_limit_is_enforced(self):
        match, _, _ = submitted(players=4)
        players = roster(match)
        too_many = [
            {"player_id": str(players[1].id), "overall": 4}
            for _ in range(settings.PEER_RATING_MAX_PER_MATCH + 1)
        ]
        with pytest.raises(ValidationError) as exc:
            submit_peer_ratings(match=match, rater=players[0], ratings=too_many)
        assert "ratings" in exc.value.message_dict


def test_the_timeline_reads_in_order():
    match, teams, scorecard = submitted()
    confirm_scorecard(scorecard=scorecard, actor=teams[TeamSide.B].captain)

    timeline = list(scorecard.events.values_list("to_status", flat=True))
    assert timeline == ["submitted", "confirmed", "locked"]


def test_stats_survive_a_resubmission():
    match, teams, scorecard = ready_to_score(players=4)
    players = roster(match)
    save_draft(
        scorecard=scorecard,
        actor=match.organiser,
        team_a_score=1,
        team_b_score=0,
        stats={str(players[0].id): {"goals": 1, "assists": 0}},
    )
    assert PlayerStat.objects.filter(scorecard=scorecard).count() == 2

    save_draft(
        scorecard=scorecard,
        actor=match.organiser,
        stats={str(players[0].id): {"goals": 1}},
    )
    # Replaced wholesale, not merged: the scorer's latest form is the truth.
    assert PlayerStat.objects.filter(scorecard=scorecard).count() == 1
