from __future__ import annotations

from datetime import date as date_type
from datetime import time as time_type

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.throttling import ReachingPeopleThrottle
from apps.players.models import PlayerProfile

from .models import JoinRequest, Match, MatchInvite, Squad, SquadInvite
from .permissions import CanViewMatch, IsMatchOrganiser
from .selectors import (
    board_matches,
    my_match_invites,
    my_squad_invites,
    squad_queryset,
    squads_for_player,
    upcoming_for_player,
    visible_matches,
)
from .serializers import (
    DecideRequestSerializer,
    DecideSerializer,
    InvitePlayerSerializer,
    JoinRequestCreateSerializer,
    JoinRequestSerializer,
    MatchDetailSerializer,
    MatchInviteSerializer,
    MatchSummarySerializer,
    RemovePlayerSerializer,
    SquadInviteSerializer,
    SquadSerializer,
    SquadSummarySerializer,
    SquadWriteSerializer,
)
from .services import (
    create_squad,
    decide_join_request,
    decide_proposed_invite,
    invite_player,
    invite_to_squad,
    leave_match,
    leave_squad,
    remove_player,
    remove_squad_member,
    request_to_join,
    respond_to_invite,
    respond_to_squad_invite,
    transfer_squad_leadership,
    withdraw_join_request,
)


def _drf_error(exc: DjangoValidationError, *, code=status.HTTP_400_BAD_REQUEST) -> Response:
    detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
    return Response(detail, status=code)


def _player_from_profile(profile_id):
    """Resolve a profile id to its account.

    Profile ids are what the UI has — a player's account id is never exposed — so every
    endpoint that names a player takes the profile id and resolves it here.
    """
    profile = get_object_or_404(PlayerProfile.objects.select_related("user"), id=profile_id)
    return profile.user


def _parse_date(raw: str | None) -> date_type | None:
    if not raw:
        return None
    try:
        return date_type.fromisoformat(raw)
    except ValueError as exc:
        raise DjangoValidationError({"date": "Use YYYY-MM-DD."}) from exc


def _parse_time(raw: str | None) -> time_type | None:
    if not raw:
        return None
    try:
        return time_type.fromisoformat(raw)
    except ValueError as exc:
        raise DjangoValidationError({"time": "Use HH:MM."}) from exc


def _parse_point(raw: str | None) -> tuple[float, float] | None:
    """``near=lat,lng`` into PostGIS ``(lng, lat)`` — same convention as Phase 02."""
    if not raw:
        return None
    try:
        latitude, longitude = (float(part) for part in raw.split(",", 1))
    except (TypeError, ValueError) as exc:
        raise DjangoValidationError({"near": "Use `near=latitude,longitude`."}) from exc
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        raise DjangoValidationError({"near": "Coordinates are out of range."})
    return (longitude, latitude)


@extend_schema_view(
    retrieve=extend_schema(operation_id="matches_retrieve", summary="One match"),
)
class MatchViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = MatchDetailSerializer
    permission_classes = [IsAuthenticated, CanViewMatch]
    queryset = Match.objects.none()

    def get_queryset(self):
        return visible_matches(self.request.user)

    def _fresh(self, match: Match) -> Response:
        return Response(
            MatchDetailSerializer(
                self.get_queryset().get(pk=match.pk), context=self.get_serializer_context()
            ).data
        )

    @extend_schema(
        operation_id="matches_board",
        summary="The match board",
        description=(
            "Upcoming matches open to requests, with spots left and the roster's average "
            "rating. Matches you are already in are excluded."
        ),
        parameters=[
            OpenApiParameter("sport", str, description="Sport slug."),
            OpenApiParameter("area", str, description="Exact area."),
            OpenApiParameter("near", str, description="`latitude,longitude`."),
            OpenApiParameter("radius_km", float),
            OpenApiParameter("date", str, description="YYYY-MM-DD, Dhaka time."),
            OpenApiParameter("time_from", str, description="HH:MM, Dhaka time."),
            OpenApiParameter("time_to", str, description="HH:MM, Dhaka time."),
            OpenApiParameter("needed_min", int, description="At least this many spots left."),
            OpenApiParameter("rating_min", int),
            OpenApiParameter("rating_max", int),
        ],
        responses={200: MatchSummarySerializer(many=True)},
    )
    @action(detail=False, methods=["get"], pagination_class=None)
    def board(self, request):
        params = request.query_params
        try:
            matches = board_matches(
                user=request.user,
                sport=params.get("sport"),
                area=params.get("area"),
                near=_parse_point(params.get("near")),
                radius_km=float(params["radius_km"]) if params.get("radius_km") else None,
                day=_parse_date(params.get("date")),
                time_from=_parse_time(params.get("time_from")),
                time_to=_parse_time(params.get("time_to")),
                needed_min=int(params["needed_min"]) if params.get("needed_min") else None,
                rating_min=int(params["rating_min"]) if params.get("rating_min") else None,
                rating_max=int(params["rating_max"]) if params.get("rating_max") else None,
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        except ValueError:
            return Response(
                {"detail": "A numeric filter was not a number."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(MatchSummarySerializer(matches[:100], many=True).data)

    @extend_schema(
        operation_id="matches_mine",
        summary="My upcoming matches",
        responses={200: MatchSummarySerializer(many=True)},
    )
    @action(detail=False, methods=["get"], url_path="mine", pagination_class=None)
    def mine(self, request):
        return Response(MatchSummarySerializer(upcoming_for_player(request.user), many=True).data)

    @extend_schema(
        operation_id="matches_request_join",
        summary="Ask to join",
        request=JoinRequestCreateSerializer,
        responses={201: JoinRequestSerializer},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="request",
        throttle_classes=[ReachingPeopleThrottle],
    )
    def request_join(self, request, pk=None):
        match = self.get_object()
        payload = JoinRequestCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            join = request_to_join(
                match=match,
                user=request.user,
                message=payload.validated_data.get("message", ""),
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(JoinRequestSerializer(join).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="matches_leave",
        summary="Drop out of a match",
        request=None,
        responses={200: MatchDetailSerializer},
    )
    @action(detail=True, methods=["post"])
    def leave(self, request, pk=None):
        match = self.get_object()
        try:
            leave_match(match=match, user=request.user)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return self._fresh(match)

    @extend_schema(
        operation_id="matches_invite",
        summary="Invite a player",
        description=(
            "A member of a **closed** squad can only propose: the leader approves, then "
            "the player accepts (DECISIONS D1). The organiser's invite skips the "
            "proposal step."
        ),
        request=InvitePlayerSerializer,
        responses={201: MatchInviteSerializer},
    )
    @action(detail=True, methods=["post"], throttle_classes=[ReachingPeopleThrottle])
    def invite(self, request, pk=None):
        match = self.get_object()
        payload = InvitePlayerSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            invite = invite_player(
                match=match,
                invited_by=request.user,
                player=_player_from_profile(payload.validated_data["player_id"]),
                message=payload.validated_data.get("message", ""),
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(MatchInviteSerializer(invite).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="matches_remove_player",
        summary="Remove a player (organiser)",
        request=RemovePlayerSerializer,
        responses={200: MatchDetailSerializer},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="remove-player",
        permission_classes=[IsAuthenticated, IsMatchOrganiser],
    )
    def remove_player(self, request, pk=None):
        match = self.get_object()
        payload = RemovePlayerSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            remove_player(
                match=match,
                actor=request.user,
                player=_player_from_profile(payload.validated_data["player_id"]),
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return self._fresh(match)


class JoinRequestDecisionView(APIView):
    """The organiser approving or declining one request."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="join_requests_decide",
        summary="Decide a join request",
        request=DecideRequestSerializer,
        responses={200: JoinRequestSerializer},
    )
    def post(self, request, request_id):
        join = get_object_or_404(
            JoinRequest.objects.select_related("match", "match__booking", "match__squad"),
            id=request_id,
        )
        payload = DecideRequestSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            decide_join_request(
                request=join,
                approver=request.user,
                approve=payload.validated_data["approve"],
                add_to_squad=payload.validated_data.get("add_to_squad", False),
                note=payload.validated_data.get("note", ""),
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(JoinRequestSerializer(join).data)


class JoinRequestWithdrawView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="join_requests_withdraw",
        summary="Withdraw my join request",
        request=None,
        responses={200: JoinRequestSerializer},
    )
    def post(self, request, request_id):
        join = get_object_or_404(JoinRequest, id=request_id)
        try:
            withdraw_join_request(request=join, user=request.user)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(JoinRequestSerializer(join).data)


class MatchInviteDecisionView(APIView):
    """The leader deciding a proposal (DECISIONS D1)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="match_invites_decide",
        summary="Approve or reject a proposed player",
        request=DecideSerializer,
        responses={200: MatchInviteSerializer},
    )
    def post(self, request, invite_id):
        invite = get_object_or_404(
            MatchInvite.objects.select_related("match", "match__booking", "match__squad"),
            id=invite_id,
        )
        payload = DecideSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            decide_proposed_invite(
                invite=invite, leader=request.user, approve=payload.validated_data["approve"]
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(MatchInviteSerializer(invite).data)


class MatchInviteRespondView(APIView):
    """The invited player accepting or declining."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="match_invites_respond",
        summary="Accept or decline an invitation",
        request=DecideSerializer,
        responses={200: MatchInviteSerializer},
    )
    def post(self, request, invite_id):
        invite = get_object_or_404(
            MatchInvite.objects.select_related("match", "match__booking", "match__squad"),
            id=invite_id,
        )
        payload = DecideSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            respond_to_invite(
                invite=invite, user=request.user, accept=payload.validated_data["approve"]
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(MatchInviteSerializer(invite).data)


class MyInvitesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="my_invites",
        summary="Invitations awaiting me",
        responses={200: MatchInviteSerializer(many=True)},
    )
    def get(self, request):
        return Response(MatchInviteSerializer(my_match_invites(request.user), many=True).data)


@extend_schema_view(
    list=extend_schema(operation_id="squads_list", summary="My squads"),
    retrieve=extend_schema(operation_id="squads_retrieve", summary="One squad"),
    create=extend_schema(
        operation_id="squads_create",
        summary="Create a squad",
        request=SquadWriteSerializer,
        responses={201: SquadSerializer},
    ),
    partial_update=extend_schema(
        operation_id="squads_update", summary="Update a squad", request=SquadWriteSerializer
    ),
)
class SquadViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    serializer_class = SquadSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "slug"
    queryset = Squad.objects.none()
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        # A squad page is readable by anyone who can reach its slug — squads are not
        # secret — but the write actions below check leadership.
        return squad_queryset() if self.action != "list" else squads_for_player(self.request.user)

    def get_serializer_class(self):
        return SquadSummarySerializer if self.action == "list" else SquadSerializer

    def create(self, request, *args, **kwargs):
        payload = SquadWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)
        sports = data.pop("sports", [])
        try:
            squad = create_squad(leader=request.user, sports=sports, **data)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(
            SquadSerializer(
                squad_queryset().get(pk=squad.pk), context=self.get_serializer_context()
            ).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        squad = self.get_object()
        from .services import is_squad_leader

        if not is_squad_leader(squad=squad, user=request.user):
            return Response(
                {"detail": "Only the leader can change the squad."},
                status=status.HTTP_403_FORBIDDEN,
            )
        payload = SquadWriteSerializer(instance=squad, data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)
        sports = data.pop("sports", None)
        for field, value in data.items():
            setattr(squad, field, value)
        squad.save()
        if sports is not None:
            squad.sports.set(sports)
        return Response(
            SquadSerializer(
                squad_queryset().get(pk=squad.pk), context=self.get_serializer_context()
            ).data
        )

    @extend_schema(
        operation_id="squads_invite",
        summary="Invite a player to the squad",
        request=InvitePlayerSerializer,
        responses={201: SquadInviteSerializer},
    )
    @action(detail=True, methods=["post"], throttle_classes=[ReachingPeopleThrottle])
    def invite(self, request, slug=None):
        squad = self.get_object()
        payload = InvitePlayerSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            invite = invite_to_squad(
                squad=squad,
                invited_by=request.user,
                player=_player_from_profile(payload.validated_data["player_id"]),
                message=payload.validated_data.get("message", ""),
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(SquadInviteSerializer(invite).data, status=status.HTTP_201_CREATED)

    @extend_schema(
        operation_id="squads_leave", summary="Leave a squad", request=None, responses={204: None}
    )
    @action(detail=True, methods=["post"])
    def leave(self, request, slug=None):
        squad = self.get_object()
        try:
            leave_squad(squad=squad, user=request.user)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)

    @extend_schema(
        operation_id="squads_remove_member",
        summary="Remove a member (leader)",
        request=RemovePlayerSerializer,
        responses={200: SquadSerializer},
    )
    @action(detail=True, methods=["post"], url_path="remove-member")
    def remove_member(self, request, slug=None):
        squad = self.get_object()
        payload = RemovePlayerSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            remove_squad_member(
                squad=squad,
                actor=request.user,
                player=_player_from_profile(payload.validated_data["player_id"]),
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(
            SquadSerializer(
                squad_queryset().get(pk=squad.pk), context=self.get_serializer_context()
            ).data
        )

    @extend_schema(
        operation_id="squads_transfer",
        summary="Hand over leadership",
        request=RemovePlayerSerializer,
        responses={200: SquadSerializer},
    )
    @action(detail=True, methods=["post"], url_path="transfer-leadership")
    def transfer(self, request, slug=None):
        squad = self.get_object()
        payload = RemovePlayerSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            transfer_squad_leadership(
                squad=squad,
                actor=request.user,
                new_leader=_player_from_profile(payload.validated_data["player_id"]),
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(
            SquadSerializer(
                squad_queryset().get(pk=squad.pk), context=self.get_serializer_context()
            ).data
        )


class SquadInviteRespondView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="squad_invites_respond",
        summary="Accept or decline a squad invitation",
        request=DecideSerializer,
        responses={200: SquadInviteSerializer},
    )
    def post(self, request, invite_id):
        invite = get_object_or_404(SquadInvite.objects.select_related("squad"), id=invite_id)
        payload = DecideSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            respond_to_squad_invite(
                invite=invite, user=request.user, accept=payload.validated_data["approve"]
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(SquadInviteSerializer(invite).data)


class MySquadInvitesView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="my_squad_invites",
        summary="Squad invitations awaiting me",
        responses={200: SquadInviteSerializer(many=True)},
    )
    def get(self, request):
        return Response(SquadInviteSerializer(my_squad_invites(request.user), many=True).data)
