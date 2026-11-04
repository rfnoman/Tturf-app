from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.cache import LEADERBOARD_TTL, cached
from apps.core.permissions import IsPlatformAdmin
from apps.core.throttling import PlayerSearchThrottle, ReportThrottle
from apps.matches.models import Match
from apps.matches.services import can_view_match
from apps.players.models import PlayerProfile
from apps.players.services import get_or_create_profile
from apps.sports.models import Sport
from apps.turfs.models import Turf

from .models import Availability, ConductReport, LeaderboardEntry
from .selectors import (
    availability_for,
    leaderboard,
    open_conduct_reports,
    search_players,
    sport_totals,
    track_record,
)
from .serializers import (
    AvailabilitySerializer,
    AvailabilityWriteSerializer,
    ConductReportCreateSerializer,
    ConductReportSerializer,
    ConductReviewSerializer,
    FairPlaySerializer,
    LeaderboardEntrySerializer,
    PlayerSearchResultSerializer,
    RatingChangeSerializer,
    TrackRecordSerializer,
)
from .services import fair_play, report_conduct, review_conduct


def _drf_error(exc: DjangoValidationError) -> Response:
    detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
    return Response(detail, status=status.HTTP_400_BAD_REQUEST)


def _int(value):
    try:
        return int(value)
    except TypeError, ValueError:
        return None


class PlayerSearchView(ListAPIView):
    """Find players to invite (DOMAIN §3)."""

    serializer_class = PlayerSearchResultSerializer
    permission_classes = [IsAuthenticated]
    # Searchable is not the same as scrapeable (Phase 11 step 4).
    throttle_classes = [PlayerSearchThrottle]

    @extend_schema(
        operation_id="player_search",
        summary="Search players",
        parameters=[
            OpenApiParameter("sport", str, description="Sport slug."),
            OpenApiParameter("position", str, description="Only with `sport`."),
            OpenApiParameter("rating_min", int),
            OpenApiParameter("rating_max", int),
            OpenApiParameter("area", str),
            OpenApiParameter("reliability_min", int),
            OpenApiParameter("played_at_turf", str, description="Turf slug."),
            OpenApiParameter("available_from", str, description="ISO datetime."),
            OpenApiParameter("available_until", str, description="ISO datetime."),
            OpenApiParameter("q", str, description="Name fragment."),
        ],
    )
    def get(self, request, *args, **kwargs):
        return super().get(request, *args, **kwargs)

    def get_queryset(self):
        # drf-spectacular introspects this with an anonymous user; there is no search to
        # describe in that case, only a shape.
        if getattr(self, "swagger_fake_view", False):
            return PlayerProfile.objects.none()

        params = self.request.query_params
        return search_players(
            viewer=self.request.user,
            sport=params.get("sport") or None,
            position=params.get("position") or None,
            rating_min=_int(params.get("rating_min")),
            rating_max=_int(params.get("rating_max")),
            area=params.get("area") or None,
            reliability_min=_int(params.get("reliability_min")),
            played_at_turf=params.get("played_at_turf") or None,
            available_from=params.get("available_from") or None,
            available_until=params.get("available_until") or None,
            query=params.get("q") or None,
        )


class MyAvailabilityView(APIView):
    """ "I'm free on Friday evening" (DOMAIN §3)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="my_availability",
        summary="My availability windows",
        responses={200: AvailabilitySerializer(many=True)},
    )
    def get(self, request):
        profile = get_or_create_profile(request.user)
        return Response(AvailabilitySerializer(availability_for(profile=profile), many=True).data)

    @extend_schema(
        operation_id="my_availability_add",
        summary="Say when I am free",
        request=AvailabilityWriteSerializer,
        responses={201: AvailabilitySerializer},
    )
    def post(self, request):
        payload = AvailabilityWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        sport = None
        if data.get("sport"):
            sport = get_object_or_404(Sport, slug=data["sport"])

        window = Availability.objects.create(
            profile=get_or_create_profile(request.user),
            sport=sport,
            starts_at=data["starts_at"],
            ends_at=data["ends_at"],
            area=data.get("area", ""),
            note=data.get("note", ""),
        )
        return Response(AvailabilitySerializer(window).data, status=status.HTTP_201_CREATED)


class MyAvailabilityDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="my_availability_delete",
        summary="Withdraw an availability window",
        responses={204: None},
    )
    def delete(self, request, availability_id):
        profile = get_or_create_profile(request.user)
        window = get_object_or_404(Availability, id=availability_id, profile=profile)
        window.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class PlayerTrackRecordView(APIView):
    """Where somebody has played, and what they did there (DOMAIN §8)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="player_track_record",
        summary="A player's record, per ground",
        parameters=[OpenApiParameter("sport", str, description="Sport slug.")],
        responses={200: TrackRecordSerializer},
    )
    def get(self, request, player_id):
        profile = get_object_or_404(PlayerProfile, id=player_id)
        sport = None
        if request.query_params.get("sport"):
            sport = get_object_or_404(Sport, slug=request.query_params["sport"])
        return Response(
            TrackRecordSerializer(
                {
                    "grounds": track_record(profile=profile, sport=sport),
                    "totals": sport_totals(profile=profile, sport=sport),
                }
            ).data
        )


class PlayerRatingHistoryView(APIView):
    """The chart, and "why did my rating change?" underneath it."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="player_rating_history",
        summary="A player's rating history in one sport",
        parameters=[OpenApiParameter("sport", str, required=True, description="Sport slug.")],
        responses={200: RatingChangeSerializer(many=True)},
    )
    def get(self, request, player_id):
        profile = get_object_or_404(PlayerProfile, id=player_id)
        sport = get_object_or_404(Sport, slug=request.query_params.get("sport", ""))
        from .models import RatingChange

        changes = (
            RatingChange.objects.filter(profile=profile, sport=sport)
            .select_related("sport", "match__booking__ground__turf")
            .order_by("-played_at")[:20]
        )
        return Response(RatingChangeSerializer(changes, many=True).data)


class PlayerFairPlayView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="player_fair_play",
        summary="A player's fair-play standing",
        responses={200: FairPlaySerializer},
    )
    def get(self, request, player_id):
        profile = get_object_or_404(PlayerProfile.objects.select_related("user"), id=player_id)
        return Response(FairPlaySerializer(fair_play(profile=profile)).data)


class MatchConductReportView(APIView):
    """Reporting somebody for what happened in a match (DOMAIN §8)."""

    permission_classes = [IsAuthenticated]
    # The review queue is the scarce resource, not the database row.
    throttle_classes = [ReportThrottle]

    @extend_schema(
        operation_id="conduct_report_create",
        summary="Report a player's conduct",
        request=ConductReportCreateSerializer,
        responses={201: ConductReportSerializer},
    )
    def post(self, request, match_id):
        match = get_object_or_404(
            Match.objects.select_related("booking__ground__turf", "sport"), id=match_id
        )
        if not can_view_match(match=match, user=request.user):
            return Response(status=status.HTTP_404_NOT_FOUND)

        payload = ConductReportCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        reported = get_object_or_404(
            PlayerProfile.objects.select_related("user"), id=payload.validated_data["player_id"]
        ).user

        try:
            report = report_conduct(
                match=match,
                reporter=request.user,
                reported=reported,
                reason=payload.validated_data["reason"],
                details=payload.validated_data.get("details", ""),
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)

        return Response(ConductReportSerializer(report).data, status=status.HTTP_201_CREATED)


class ConductQueueView(APIView):
    """The admin review queue."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    @extend_schema(
        operation_id="conduct_queue",
        summary="Conduct reports awaiting review",
        responses={200: ConductReportSerializer(many=True)},
    )
    def get(self, request):
        return Response(ConductReportSerializer(open_conduct_reports(), many=True).data)


class ConductReviewView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    @extend_schema(
        operation_id="conduct_review",
        summary="Uphold or dismiss a report",
        request=ConductReviewSerializer,
        responses={200: ConductReportSerializer},
    )
    def post(self, request, report_id):
        report = get_object_or_404(
            ConductReport.objects.select_related("match", "reporter", "reported"), id=report_id
        )
        payload = ConductReviewSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            report = review_conduct(
                report=report,
                reviewer=request.user,
                uphold=payload.validated_data["uphold"],
                note=payload.validated_data.get("note", ""),
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(ConductReportSerializer(report).data)


class LeaderboardView(APIView):
    """A turf's or the platform's board (DOMAIN §8)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="leaderboard",
        summary="A leaderboard",
        parameters=[
            OpenApiParameter("sport", str, required=True, description="Sport slug."),
            OpenApiParameter("turf", str, description="Turf slug; omit for platform-wide."),
            OpenApiParameter(
                "metric", str, description="rating | motm | wins | top_stat. Default rating."
            ),
            OpenApiParameter("stat_key", str, description='Only with metric="top_stat".'),
            OpenApiParameter("period", str, description="month | all_time. Default month."),
        ],
        responses={200: LeaderboardEntrySerializer(many=True)},
    )
    def get(self, request):
        params = request.query_params
        sport = get_object_or_404(Sport, slug=params.get("sport", ""))
        turf = None
        if params.get("turf"):
            turf = get_object_or_404(Turf, slug=params["turf"])

        metric = params.get("metric") or LeaderboardEntry.Metric.RATING
        if metric not in LeaderboardEntry.Metric.values:
            return Response({"metric": "Unknown metric."}, status=status.HTTP_400_BAD_REQUEST)
        period = params.get("period") or LeaderboardEntry.Period.MONTH
        if period not in LeaderboardEntry.Period.values:
            return Response({"period": "Unknown period."}, status=status.HTTP_400_BAD_REQUEST)

        stat_key = params.get("stat_key", "")

        # The board is rewritten nightly and read all day, by every player who opens a
        # turf page. It is the same answer for all of them, so it is built once.
        def build():
            rows = leaderboard(
                sport=sport,
                turf=turf,
                metric=metric,
                stat_key=stat_key,
                period=period,
            )
            return LeaderboardEntrySerializer(rows, many=True).data

        key = f"{sport.slug}:{turf.slug if turf else ''}:{metric}:{stat_key}:{period}"
        return Response(cached("leaderboard", key, LEADERBOARD_TTL, build))
