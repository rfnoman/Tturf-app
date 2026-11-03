from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    JoinRequestDecisionView,
    JoinRequestWithdrawView,
    MatchInviteDecisionView,
    MatchInviteRespondView,
    MatchViewSet,
    MyInvitesView,
    MySquadInvitesView,
    SquadInviteRespondView,
    SquadViewSet,
)

router = SimpleRouter(trailing_slash=False)
router.register("matches", MatchViewSet, basename="match")
router.register("squads", SquadViewSet, basename="squad")

urlpatterns = [
    path("me/invites", MyInvitesView.as_view(), name="my-invites"),
    path("me/squad-invites", MySquadInvitesView.as_view(), name="my-squad-invites"),
    path(
        "join-requests/<uuid:request_id>/decide",
        JoinRequestDecisionView.as_view(),
        name="join-request-decide",
    ),
    path(
        "join-requests/<uuid:request_id>/withdraw",
        JoinRequestWithdrawView.as_view(),
        name="join-request-withdraw",
    ),
    path(
        "match-invites/<uuid:invite_id>/decide",
        MatchInviteDecisionView.as_view(),
        name="match-invite-decide",
    ),
    path(
        "match-invites/<uuid:invite_id>/respond",
        MatchInviteRespondView.as_view(),
        name="match-invite-respond",
    ),
    path(
        "squad-invites/<uuid:invite_id>/respond",
        SquadInviteRespondView.as_view(),
        name="squad-invite-respond",
    ),
    path("", include(router.urls)),
]
