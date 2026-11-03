"""Turf routes.

Nested resources are spelled out rather than pulled in through a nested-router package:
the owner area has one shape (`/me/turfs/{slug}/…`), it is five resources deep at most,
and an explicit list keeps the dependency count down (CLAUDE.md).
"""

from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    AdminTurfViewSet,
    AmenityListView,
    GroundAvailabilityView,
    MyClosureViewSet,
    MyGroundViewSet,
    MyOperatingHoursViewSet,
    MyPriceRuleViewSet,
    MyTurfPhotoViewSet,
    MyTurfViewSet,
    StaffMembershipViewSet,
    TurfStaffRemoveView,
    TurfViewSet,
)

router = SimpleRouter(trailing_slash=False)
router.register("turfs", TurfViewSet, basename="turf")
router.register("me/turfs", MyTurfViewSet, basename="my-turf")
router.register("me/memberships", StaffMembershipViewSet, basename="my-membership")
router.register("admin/turfs", AdminTurfViewSet, basename="admin-turf")

LIST = {"get": "list", "post": "create"}
DETAIL = {"get": "retrieve", "patch": "partial_update", "delete": "destroy"}

nested = [
    path(
        "me/turfs/<slug:slug>/grounds",
        MyGroundViewSet.as_view(LIST),
        name="my-ground-list",
    ),
    path(
        "me/turfs/<slug:slug>/grounds/<uuid:pk>",
        MyGroundViewSet.as_view(DETAIL),
        name="my-ground-detail",
    ),
    path(
        "me/turfs/<slug:slug>/grounds/<uuid:pk>/activate",
        MyGroundViewSet.as_view({"post": "activate"}),
        name="my-ground-activate",
    ),
    path(
        "me/turfs/<slug:slug>/grounds/<uuid:pk>/deactivate",
        MyGroundViewSet.as_view({"post": "deactivate"}),
        name="my-ground-deactivate",
    ),
    path(
        "me/turfs/<slug:slug>/grounds/<uuid:pk>/price-coverage",
        MyGroundViewSet.as_view({"get": "price_coverage"}),
        name="my-ground-price-coverage",
    ),
    path(
        "me/turfs/<slug:slug>/grounds/<uuid:ground_pk>/prices",
        MyPriceRuleViewSet.as_view(LIST),
        name="my-price-list",
    ),
    path(
        "me/turfs/<slug:slug>/grounds/<uuid:ground_pk>/prices/<uuid:pk>",
        MyPriceRuleViewSet.as_view(DETAIL),
        name="my-price-detail",
    ),
    path("me/turfs/<slug:slug>/hours", MyOperatingHoursViewSet.as_view(LIST), name="my-hours-list"),
    path(
        "me/turfs/<slug:slug>/hours/<uuid:pk>",
        MyOperatingHoursViewSet.as_view(DETAIL),
        name="my-hours-detail",
    ),
    path("me/turfs/<slug:slug>/closures", MyClosureViewSet.as_view(LIST), name="my-closure-list"),
    path(
        "me/turfs/<slug:slug>/closures/<uuid:pk>",
        MyClosureViewSet.as_view(DETAIL),
        name="my-closure-detail",
    ),
    path("me/turfs/<slug:slug>/photos", MyTurfPhotoViewSet.as_view(LIST), name="my-photo-list"),
    path(
        "me/turfs/<slug:slug>/photos/<uuid:pk>",
        MyTurfPhotoViewSet.as_view(DETAIL),
        name="my-photo-detail",
    ),
    path(
        "me/turfs/<slug:slug>/staff/<uuid:membership_id>",
        TurfStaffRemoveView.as_view(),
        name="my-staff-remove",
    ),
]

urlpatterns = [
    path("amenities", AmenityListView.as_view(), name="amenities"),
    path(
        "grounds/<uuid:ground_id>/availability",
        GroundAvailabilityView.as_view(),
        name="ground-availability",
    ),
    *nested,
    path("", include(router.urls)),
]
