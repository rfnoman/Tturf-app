from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    AdminSportProposalViewSet,
    AttributeListView,
    SportProposalViewSet,
    SportViewSet,
)

# No trailing slashes anywhere in this API: /api/v1/me, /api/v1/health and
# everything else from Phase 00 are slash-free, so the routers must match.
router = SimpleRouter(trailing_slash=False)
router.register("sports", SportViewSet, basename="sport")
router.register("sport-proposals", SportProposalViewSet, basename="sport-proposal")
router.register("admin/sport-proposals", AdminSportProposalViewSet, basename="admin-sport-proposal")

urlpatterns = [
    path("attributes", AttributeListView.as_view(), name="attributes"),
    path("", include(router.urls)),
]
