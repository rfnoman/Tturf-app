from django.urls import path

from .views import (
    ClientConfigView,
    HealthView,
    PlatformDashboardView,
    PlayerLookupView,
)

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
    path("config", ClientConfigView.as_view(), name="client-config"),
    path("admin/dashboard", PlatformDashboardView.as_view(), name="platform-dashboard"),
    path("admin/players", PlayerLookupView.as_view(), name="player-lookup"),
]
