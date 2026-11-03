from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.matches.models import Match
from apps.matches.selectors import visible_matches
from apps.matches.services import can_view_match
from apps.players.models import PlayerProfile

from .models import Scorecard, ScorecardStatus
from .selectors import player_results, public_scorecard_queryset, scorecard_queryset
from .serializers import (
    AssignScorerSerializer,
    DisputeSerializer,
    MatchTeamSerializer,
    MotmVoteSerializer,
    PeerRatingsSerializer,
    PublicScorecardSerializer,
    ResolveSerializer,
    ResultSummarySerializer,
    SaveScorecardSerializer,
    ScorecardSerializer,
    SetCaptainSerializer,
    SetTeamsSerializer,
)
from .services import (
    assign_scorer,
    auto_balance_teams,
    cast_motm_vote,
    confirm_scorecard,
    dispute_scorecard,
    get_or_create_scorecard,
    resolve_dispute,
    save_draft,
    set_captain,
    set_teams,
    submit_peer_ratings,
    submit_scorecard,
)


def _drf_error(exc: DjangoValidationError) -> Response:
    detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
    return Response(detail, status=status.HTTP_400_BAD_REQUEST)


def _player_from_profile(profile_id):
    """Profile ids are what the UI carries; account ids are never exposed (D39)."""
    if profile_id is None:
        return None
    profile = get_object_or_404(PlayerProfile.objects.select_related("user"), id=profile_id)
    return profile.user


class MatchScopedView(APIView):
    """Shared lookup: a match this reader may see."""

    permission_classes = [IsAuthenticated]

    def get_match(self, request, match_id) -> Match:
        match = get_object_or_404(visible_matches(request.user), id=match_id)
        if not can_view_match(match=match, user=request.user):
            # Belt and braces: the queryset already scopes it.
            self.permission_denied(request, message="You cannot see this match.")
        return match

    def render(self, request, match: Match) -> Response:
        scorecard = scorecard_queryset().get(match=match)
        return Response(ScorecardSerializer(scorecard, context={"request": request}).data)


class MatchTeamsView(MatchScopedView):
    """The two sides, and setting them."""

    @extend_schema(
        operation_id="match_teams",
        summary="Teams for a match",
        responses={200: MatchTeamSerializer(many=True)},
    )
    def get(self, request, match_id):
        match = self.get_match(request, match_id)
        from .services import ensure_teams

        ensure_teams(match=match)
        return Response(MatchTeamSerializer(match.teams.order_by("side"), many=True).data)

    @extend_schema(
        operation_id="match_teams_set",
        summary="Split the roster into two teams",
        request=SetTeamsSerializer,
        responses={200: MatchTeamSerializer(many=True)},
    )
    def post(self, request, match_id):
        match = self.get_match(request, match_id)
        payload = SetTeamsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            teams = set_teams(
                match=match, assignments=payload.validated_data["assignments"], actor=request.user
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(MatchTeamSerializer(teams, many=True).data)


class MatchAutoBalanceView(MatchScopedView):
    @extend_schema(
        operation_id="match_teams_auto_balance",
        summary="Auto-balance the teams by rating",
        request=None,
        responses={200: MatchTeamSerializer(many=True)},
    )
    def post(self, request, match_id):
        match = self.get_match(request, match_id)
        try:
            teams = auto_balance_teams(match=match, actor=request.user)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(MatchTeamSerializer(teams, many=True).data)


class MatchCaptainView(MatchScopedView):
    @extend_schema(
        operation_id="match_teams_set_captain",
        summary="Name a team's captain",
        request=SetCaptainSerializer,
        responses={200: MatchTeamSerializer},
    )
    def post(self, request, match_id):
        match = self.get_match(request, match_id)
        payload = SetCaptainSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            team = set_captain(
                match=match,
                side=payload.validated_data["side"],
                player=_player_from_profile(payload.validated_data.get("player_id")),
                actor=request.user,
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(MatchTeamSerializer(team).data)


class ScorecardView(MatchScopedView):
    """The scorecard, and the scorer's draft."""

    @extend_schema(
        operation_id="scorecard_retrieve",
        summary="A match's scorecard",
        description="Created in draft on first access, so this never 404s for a visible match.",
        responses={200: ScorecardSerializer},
    )
    def get(self, request, match_id):
        match = self.get_match(request, match_id)
        get_or_create_scorecard(match=match)
        return self.render(request, match)

    @extend_schema(
        operation_id="scorecard_save",
        summary="Save the scorer's draft",
        description="Not validated: a scorer filling in a phone form is not blocked halfway.",
        request=SaveScorecardSerializer,
        responses={200: ScorecardSerializer},
    )
    def patch(self, request, match_id):
        match = self.get_match(request, match_id)
        scorecard = get_or_create_scorecard(match=match)
        payload = SaveScorecardSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            save_draft(scorecard=scorecard, actor=request.user, **payload.validated_data)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return self.render(request, match)


class ScorecardSubmitView(MatchScopedView):
    @extend_schema(
        operation_id="scorecard_submit",
        summary="Submit the scorecard",
        description=(
            "Runs the sport's validators. A 400 maps each message to the field it is "
            "about, so the entry form can show them inline."
        ),
        request=None,
        responses={200: ScorecardSerializer},
    )
    def post(self, request, match_id):
        match = self.get_match(request, match_id)
        scorecard = get_or_create_scorecard(match=match)
        try:
            submit_scorecard(scorecard=scorecard, actor=request.user)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return self.render(request, match)


class ScorecardConfirmView(MatchScopedView):
    @extend_schema(
        operation_id="scorecard_confirm",
        summary="Confirm the scorecard (opposing captain or staff)",
        request=None,
        responses={200: ScorecardSerializer},
    )
    def post(self, request, match_id):
        match = self.get_match(request, match_id)
        scorecard = get_object_or_404(Scorecard, match=match)
        try:
            confirm_scorecard(scorecard=scorecard, actor=request.user)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return self.render(request, match)


class ScorecardDisputeView(MatchScopedView):
    @extend_schema(
        operation_id="scorecard_dispute",
        summary="Dispute the scorecard",
        request=DisputeSerializer,
        responses={200: ScorecardSerializer},
    )
    def post(self, request, match_id):
        match = self.get_match(request, match_id)
        scorecard = get_object_or_404(Scorecard, match=match)
        payload = DisputeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            dispute_scorecard(
                scorecard=scorecard, actor=request.user, reason=payload.validated_data["reason"]
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return self.render(request, match)


class ScorecardResolveView(MatchScopedView):
    @extend_schema(
        operation_id="scorecard_resolve",
        summary="Resolve a dispute (turf staff or admin)",
        description="Corrects the card if needed, then confirms and locks it.",
        request=ResolveSerializer,
        responses={200: ScorecardSerializer},
    )
    def post(self, request, match_id):
        match = self.get_match(request, match_id)
        scorecard = get_object_or_404(Scorecard, match=match)
        payload = ResolveSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            resolve_dispute(scorecard=scorecard, actor=request.user, **payload.validated_data)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return self.render(request, match)


class ScorecardScorerView(MatchScopedView):
    @extend_schema(
        operation_id="scorecard_assign_scorer",
        summary="Hand scoring to somebody else",
        request=AssignScorerSerializer,
        responses={200: ScorecardSerializer},
    )
    def post(self, request, match_id):
        match = self.get_match(request, match_id)
        scorecard = get_or_create_scorecard(match=match)
        payload = AssignScorerSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            assign_scorer(
                scorecard=scorecard,
                actor=request.user,
                scorer=_player_from_profile(payload.validated_data["player_id"]),
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return self.render(request, match)


class MotmVoteView(MatchScopedView):
    @extend_schema(
        operation_id="motm_vote",
        summary="Vote for man of the match",
        request=MotmVoteSerializer,
        responses={200: ScorecardSerializer},
    )
    def post(self, request, match_id):
        match = self.get_match(request, match_id)
        payload = MotmVoteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            cast_motm_vote(
                match=match,
                voter=request.user,
                nominee=_player_from_profile(payload.validated_data["player_id"]),
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return self.render(request, match)


class PeerRatingView(MatchScopedView):
    @extend_schema(
        operation_id="peer_ratings_submit",
        summary="Rate the other players",
        description="Anonymous to the recipients; re-submitting replaces an earlier rating.",
        request=PeerRatingsSerializer,
        responses={
            200: inline_serializer(
                name="PeerRatingsSaved", fields={"saved": serializers.IntegerField()}
            )
        },
    )
    def post(self, request, match_id):
        match = self.get_match(request, match_id)
        payload = PeerRatingsSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        # The API names players by profile id (DECISIONS D39); the service works in
        # accounts, so they are resolved here rather than leaking profile ids inward.
        ratings = [
            {
                "player_id": str(_player_from_profile(entry["player_id"]).id),
                "overall": entry["overall"],
                "skill_taps": entry.get("skill_taps") or [],
            }
            for entry in payload.validated_data["ratings"]
        ]

        try:
            saved = submit_peer_ratings(match=match, rater=request.user, ratings=ratings)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response({"saved": len(saved)})


class PublicScorecardView(APIView):
    """The shareable scorecard. **No sign-in required** (phase 05 acceptance).

    Only locked scorecards: an unfinished or disputed card is not a result, and a link
    that showed one would be shared before it was true.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="public_scorecard",
        summary="Public scorecard",
        description="Locked scorecards only. No authentication required — this is the shared link.",
        responses={200: PublicScorecardSerializer},
    )
    def get(self, request, match_id):
        scorecard = get_object_or_404(
            public_scorecard_queryset(), match_id=match_id, status=ScorecardStatus.LOCKED
        )
        return Response(PublicScorecardSerializer(scorecard, context={}).data)


class PlayerResultsView(APIView):
    """A player's recent results, for the profile track record."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="player_results",
        summary="A player's recent results",
        responses={200: ResultSummarySerializer(many=True)},
    )
    def get(self, request, player_id):
        profile = get_object_or_404(PlayerProfile.objects.select_related("user"), id=player_id)
        return Response(ResultSummarySerializer(player_results(profile.user), many=True).data)
