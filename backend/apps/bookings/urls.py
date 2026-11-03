from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import (
    BookingViewSet,
    MyBookingsView,
    TurfBookingsView,
    TurfPendingBookingsView,
    WalkInBookingView,
)

router = SimpleRouter(trailing_slash=False)
router.register("bookings", BookingViewSet, basename="booking")

urlpatterns = [
    path("me/bookings", MyBookingsView.as_view(), name="my-bookings"),
    path(
        "me/turfs/<slug:slug>/bookings",
        TurfBookingsView.as_view(),
        name="turf-bookings",
    ),
    path(
        "me/turfs/<slug:slug>/bookings/pending",
        TurfPendingBookingsView.as_view(),
        name="turf-bookings-pending",
    ),
    path(
        "me/turfs/<slug:slug>/bookings/walk-in",
        WalkInBookingView.as_view(),
        name="turf-bookings-walk-in",
    ),
    path("", include(router.urls)),
]
