from __future__ import annotations

from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .utils import setting


class HealthView(APIView):
    """Liveness/readiness probe: reports database and PostGIS availability."""

    authentication_classes: list = []
    permission_classes = [AllowAny]
    # A load balancer polling this must never be told to slow down.
    throttle_classes: list = []

    @extend_schema(
        operation_id="health",
        summary="Service health",
        responses={
            200: inline_serializer(
                name="Health",
                fields={
                    "status": serializers.CharField(),
                    "database": serializers.CharField(),
                    "postgis": serializers.CharField(allow_null=True),
                    "version": serializers.CharField(),
                },
            )
        },
    )
    def get(self, request):
        database = "ok"
        postgis = None
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT postgis_version()")
                row = cursor.fetchone()
                postgis = row[0] if row else None
        except Exception:  # pragma: no cover - only hit when the DB is down
            database = "error"

        payload = {
            "status": "ok" if database == "ok" else "degraded",
            "database": database,
            "postgis": postgis,
            "version": settings.SPECTACULAR_SETTINGS["VERSION"],
        }
        http_status = (
            status.HTTP_200_OK if database == "ok" else status.HTTP_503_SERVICE_UNAVAILABLE
        )
        return Response(payload, status=http_status)


class ClientConfigView(APIView):
    """Configurable business rules the frontend needs to render correct controls.

    CLAUDE.md forbids hard-coding these rules, and that has to hold on both sides of the
    wire: an onboarding slider whose ceiling is a literal would silently disagree with
    the server's ``SELF_ASSESSED_RATING_CAP`` the moment someone changed it. Serving them
    from here means ``apps/core/utils.setting`` stays the single source, so when the
    ``PlatformSetting`` model arrives the frontend inherits database-backed values with
    no change.

    Public on purpose: these are UI constants, not secrets.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]
    # Unthrottled on purpose. Every server-rendered page reads this, and they all reach
    # Django from the frontend server's single address — so an IP-keyed limit here
    # throttles the site, not an attacker. The response is a handful of constants.
    throttle_classes: list = []

    @extend_schema(
        operation_id="client_config",
        summary="Client configuration",
        description="Business rules and limits the UI needs. Safe to cache for minutes.",
        responses={
            200: inline_serializer(
                name="ClientConfig",
                fields={
                    "rating_min": serializers.IntegerField(),
                    "rating_max": serializers.IntegerField(),
                    "self_assessed_rating_cap": serializers.IntegerField(),
                    "onboarding_default_rating": serializers.IntegerField(),
                    "rating_provisional_matches": serializers.IntegerField(),
                    "default_player_weight_kg": serializers.IntegerField(),
                    "booking_horizon_days": serializers.IntegerField(),
                    "turf_delivery_cutoff_hours": serializers.IntegerField(),
                    "currency": serializers.CharField(),
                    "time_zone": serializers.CharField(),
                    "week_starts_on": serializers.IntegerField(),
                    "vapid_public_key": serializers.CharField(allow_blank=True),
                },
            )
        },
    )
    def get(self, request):
        return Response(
            {
                "rating_min": 1,
                "rating_max": 99,
                "self_assessed_rating_cap": setting("SELF_ASSESSED_RATING_CAP"),
                "onboarding_default_rating": setting("ONBOARDING_DEFAULT_RATING"),
                "rating_provisional_matches": setting("RATING_PROVISIONAL_MATCHES"),
                "default_player_weight_kg": setting("DEFAULT_PLAYER_WEIGHT_KG"),
                "booking_horizon_days": setting("BOOKING_HORIZON_DAYS"),
                "turf_delivery_cutoff_hours": setting("TURF_DELIVERY_CUTOFF_HOURS"),
                "currency": "BDT",
                "time_zone": settings.TIME_ZONE,
                "week_starts_on": setting("FITNESS_WEEK_STARTS_ON"),
                # The *public* half of the VAPID pair, which is what a browser needs to
                # subscribe. Empty in development, where push is switched off entirely.
                "vapid_public_key": settings.VAPID_PUBLIC_KEY,
            }
        )
