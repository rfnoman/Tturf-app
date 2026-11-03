from django.urls import path

from .views import (
    MyProfileView,
    MySportDetailView,
    MySportsView,
    OnboardingView,
    PlayerDetailView,
)

urlpatterns = [
    path("me/profile", MyProfileView.as_view(), name="my-profile"),
    path("me/onboarding", OnboardingView.as_view(), name="my-onboarding"),
    path("me/sports", MySportsView.as_view(), name="my-sports"),
    path("me/sports/<slug:slug>", MySportDetailView.as_view(), name="my-sport-detail"),
    path("players/<uuid:player_id>", PlayerDetailView.as_view(), name="player-detail"),
]
