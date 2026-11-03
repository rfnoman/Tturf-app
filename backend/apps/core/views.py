from __future__ import annotations

from django.conf import settings
from django.db import connection
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class HealthView(APIView):
    """Liveness/readiness probe: reports database and PostGIS availability."""

    authentication_classes: list = []
    permission_classes = [AllowAny]

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
