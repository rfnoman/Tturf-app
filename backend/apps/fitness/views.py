"""Fitness endpoints: activity, goals, bundles, reminders and push."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.utils import now, to_dhaka
from apps.matches.models import Match
from apps.sports.models import Sport

from .models import ActivityLog, Bundle, PushSubscription
from .serializers import (
    ActivityLogSerializer,
    BundleResultSerializer,
    BundleSerializer,
    DashboardSerializer,
    GoalProgressSerializer,
    ManualActivitySerializer,
    PushSubscriptionSerializer,
    ReminderPreferenceSerializer,
    SetGoalSerializer,
    WeeklySummarySerializer,
)
from .services import (
    add_bundle_to_cart,
    goal_progress,
    log_manual_activity,
    reminder_preference,
    set_goal,
    streak_for,
    suggested_bundles,
    weekly_summary,
)


def _error(exc: DjangoValidationError) -> Response:
    detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
    return Response(detail, status=status.HTTP_400_BAD_REQUEST)


class DashboardView(APIView):
    """The home screen in one request: the week, the streak, the goals, the last few."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="fitness_dashboard",
        summary="This player's week",
        responses={200: DashboardSerializer},
    )
    def get(self, request):
        return Response(
            DashboardSerializer(
                {
                    "week": weekly_summary(player=request.user),
                    "streak": streak_for(player=request.user),
                    "goals": goal_progress(player=request.user),
                    "recent": ActivityLog.objects.filter(player=request.user)[:10],
                }
            ).data
        )


class ActivityView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="activity_list",
        summary="My activity",
        parameters=[OpenApiParameter("days", int, description="How far back. Default 90.")],
        responses={200: ActivityLogSerializer(many=True)},
    )
    def get(self, request):
        from datetime import timedelta

        try:
            days = int(request.query_params.get("days", 90))
        except TypeError, ValueError:
            days = 90

        since = to_dhaka(now()).date() - timedelta(days=min(days, 365))
        logs = ActivityLog.objects.filter(
            player=request.user, happened_on__gte=since
        ).select_related("sport", "match__booking__ground__turf")
        return Response(ActivityLogSerializer(logs, many=True).data)

    @extend_schema(
        operation_id="activity_add",
        summary="Add something I did",
        request=ManualActivitySerializer,
        responses={201: ActivityLogSerializer},
    )
    def post(self, request):
        payload = ManualActivitySerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        sport = None
        if data.get("sport"):
            sport = get_object_or_404(Sport, slug=data["sport"])

        try:
            log = log_manual_activity(
                player=request.user,
                minutes=data["minutes"],
                happened_on=data.get("happened_on"),
                sport=sport,
                note=data.get("note", ""),
            )
        except DjangoValidationError as exc:
            return _error(exc)

        return Response(ActivityLogSerializer(log).data, status=status.HTTP_201_CREATED)


class WeekView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="activity_week",
        summary="One week's totals",
        parameters=[OpenApiParameter("date", str, description="Any day in the week (Dhaka).")],
        responses={200: WeeklySummarySerializer},
    )
    def get(self, request):
        from datetime import date as date_type

        day = None
        if request.query_params.get("date"):
            try:
                day = date_type.fromisoformat(request.query_params["date"])
            except ValueError:
                return Response({"date": "Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        return Response(WeeklySummarySerializer(weekly_summary(player=request.user, day=day)).data)


class GoalView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="goals_list",
        summary="My goals and where they stand",
        responses={200: GoalProgressSerializer(many=True)},
    )
    def get(self, request):
        return Response(GoalProgressSerializer(goal_progress(player=request.user), many=True).data)

    @extend_schema(
        operation_id="goals_set",
        summary="Set a goal (0 retires it)",
        request=SetGoalSerializer,
        responses={200: GoalProgressSerializer(many=True)},
    )
    def post(self, request):
        payload = SetGoalSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            set_goal(
                player=request.user,
                type=payload.validated_data["type"],
                target=payload.validated_data["target"],
            )
        except DjangoValidationError as exc:
            return _error(exc)

        return Response(GoalProgressSerializer(goal_progress(player=request.user), many=True).data)


class BundleListView(APIView):
    """Curated kits (DOMAIN §10)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="bundles_list",
        summary="Bundles",
        parameters=[OpenApiParameter("match", str, description="Tailor them to a match.")],
        responses={200: BundleSerializer(many=True)},
    )
    def get(self, request):
        match = None
        if request.query_params.get("match"):
            match = Match.objects.filter(id=request.query_params["match"]).first()
        return Response(
            BundleSerializer(suggested_bundles(player=request.user, match=match), many=True).data
        )


class BundleAddView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="bundle_add_to_cart",
        summary="Add a whole bundle to the cart",
        request=None,
        responses={200: BundleResultSerializer},
    )
    def post(self, request, slug):
        bundle = get_object_or_404(
            Bundle.objects.prefetch_related("items__product"), slug=slug, is_active=True
        )
        try:
            result = add_bundle_to_cart(player=request.user, bundle=bundle)
        except DjangoValidationError as exc:
            return _error(exc)

        return Response(BundleResultSerializer(result).data)


class ReminderPreferenceView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="reminders_read",
        summary="My reminder settings",
        responses={200: ReminderPreferenceSerializer},
    )
    def get(self, request):
        return Response(ReminderPreferenceSerializer(reminder_preference(request.user)).data)

    @extend_schema(
        operation_id="reminders_update",
        summary="Change my reminder settings",
        request=ReminderPreferenceSerializer,
        responses={200: ReminderPreferenceSerializer},
    )
    def patch(self, request):
        preference = reminder_preference(request.user)
        payload = ReminderPreferenceSerializer(preference, data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        payload.save()
        return Response(payload.data)


class PushSubscribeView(APIView):
    """A browser signing up for push (DECISIONS D55)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="push_subscribe",
        summary="Register this browser for push",
        request=PushSubscriptionSerializer,
        responses={201: None},
    )
    def post(self, request):
        payload = PushSubscriptionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        PushSubscription.objects.update_or_create(
            endpoint=data["endpoint"],
            defaults={
                "player": request.user,
                "p256dh": data["p256dh"],
                "auth": data["auth"],
                "user_agent": data.get("user_agent", "")[:200],
            },
        )
        # Registering a browser is the player saying yes; the preference follows it.
        preference = reminder_preference(request.user)
        if not preference.push_enabled:
            preference.push_enabled = True
            preference.save(update_fields=["push_enabled", "updated_at"])

        return Response(status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="push_unsubscribe",
        summary="Forget this browser",
        responses={204: None},
    )
    def delete(self, request):
        endpoint = request.query_params.get("endpoint", "")
        PushSubscription.objects.filter(player=request.user, endpoint=endpoint).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class NotificationStreamView(APIView):
    """The SSE stream (DECISIONS D54).

    Excluded from the schema: it is a text/event-stream, not JSON, and describing it as
    an operation with a response body would be a lie.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(exclude=True)
    def get(self, request):
        from apps.notifications.stream import event_stream

        response = StreamingHttpResponse(
            event_stream(user_id=request.user.id),
            content_type="text/event-stream",
        )
        # Nginx buffers by default, which would hold every event until the buffer fills.
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
