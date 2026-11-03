from django.urls import path

from .views import (
    ConductQueueView,
    ConductReviewView,
    LeaderboardView,
    MatchConductReportView,
    MyAvailabilityDetailView,
    MyAvailabilityView,
    PlayerFairPlayView,
    PlayerRatingHistoryView,
    PlayerSearchView,
    PlayerTrackRecordView,
)

urlpatterns = [
    path("players/search", PlayerSearchView.as_view(), name="player-search"),
    path("me/availability", MyAvailabilityView.as_view(), name="my-availability"),
    path(
        "me/availability/<uuid:availability_id>",
        MyAvailabilityDetailView.as_view(),
        name="my-availability-detail",
    ),
    path(
        "players/<uuid:player_id>/track-record",
        PlayerTrackRecordView.as_view(),
        name="player-track-record",
    ),
    path(
        "players/<uuid:player_id>/rating-history",
        PlayerRatingHistoryView.as_view(),
        name="player-rating-history",
    ),
    path(
        "players/<uuid:player_id>/fair-play",
        PlayerFairPlayView.as_view(),
        name="player-fair-play",
    ),
    path(
        "matches/<uuid:match_id>/conduct-reports",
        MatchConductReportView.as_view(),
        name="match-conduct-report",
    ),
    path("admin/conduct-reports", ConductQueueView.as_view(), name="conduct-queue"),
    path(
        "admin/conduct-reports/<uuid:report_id>/review",
        ConductReviewView.as_view(),
        name="conduct-review",
    ),
    path("leaderboard", LeaderboardView.as_view(), name="leaderboard"),
]
