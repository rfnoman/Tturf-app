from django.urls import path

from .views import (
    MatchAutoBalanceView,
    MatchCaptainView,
    MatchTeamsView,
    MotmVoteView,
    PeerRatingView,
    PlayerResultsView,
    PublicScorecardView,
    ScorecardConfirmView,
    ScorecardDisputeView,
    ScorecardResolveView,
    ScorecardScorerView,
    ScorecardSubmitView,
    ScorecardView,
)

urlpatterns = [
    path("matches/<uuid:match_id>/teams", MatchTeamsView.as_view(), name="match-teams"),
    path(
        "matches/<uuid:match_id>/teams/auto-balance",
        MatchAutoBalanceView.as_view(),
        name="match-teams-auto-balance",
    ),
    path(
        "matches/<uuid:match_id>/teams/captain",
        MatchCaptainView.as_view(),
        name="match-teams-captain",
    ),
    path("matches/<uuid:match_id>/scorecard", ScorecardView.as_view(), name="scorecard"),
    path(
        "matches/<uuid:match_id>/scorecard/submit",
        ScorecardSubmitView.as_view(),
        name="scorecard-submit",
    ),
    path(
        "matches/<uuid:match_id>/scorecard/confirm",
        ScorecardConfirmView.as_view(),
        name="scorecard-confirm",
    ),
    path(
        "matches/<uuid:match_id>/scorecard/dispute",
        ScorecardDisputeView.as_view(),
        name="scorecard-dispute",
    ),
    path(
        "matches/<uuid:match_id>/scorecard/resolve",
        ScorecardResolveView.as_view(),
        name="scorecard-resolve",
    ),
    path(
        "matches/<uuid:match_id>/scorecard/scorer",
        ScorecardScorerView.as_view(),
        name="scorecard-scorer",
    ),
    path("matches/<uuid:match_id>/motm", MotmVoteView.as_view(), name="motm-vote"),
    path(
        "matches/<uuid:match_id>/peer-ratings",
        PeerRatingView.as_view(),
        name="peer-ratings",
    ),
    # Public, unauthenticated: this is the shareable link.
    path(
        "public/matches/<uuid:match_id>/scorecard",
        PublicScorecardView.as_view(),
        name="public-scorecard",
    ),
    path("players/<uuid:player_id>/results", PlayerResultsView.as_view(), name="player-results"),
]
