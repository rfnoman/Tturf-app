from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsPlatformAdmin

from .models import Attribute, Sport, SportProposal
from .selectors import all_sport_proposals, sport_catalogue, sport_proposals_for
from .serializers import (
    AttributeSerializer,
    SportProposalApproveSerializer,
    SportProposalCreateSerializer,
    SportProposalMergeSerializer,
    SportProposalRejectSerializer,
    SportProposalSerializer,
    SportSerializer,
)
from .services import (
    approve_sport_proposal,
    create_sport_proposal,
    merge_sport_proposal,
    reject_sport_proposal,
)


def _drf_error(exc: DjangoValidationError) -> Response:
    """Render a service-layer ``ValidationError`` as a DRF 400.

    Services raise Django's ``ValidationError`` so they stay usable from management
    commands and Celery tasks; the HTTP layer is what translates it.
    """
    detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
    return Response(detail, status=status.HTTP_400_BAD_REQUEST)


@extend_schema_view(
    list=extend_schema(
        operation_id="sports_list",
        summary="Sports catalogue",
        description=(
            "Every active sport with its formats, skills, attribute weights and scorecard "
            "stat definitions. One call is enough to render onboarding."
        ),
        parameters=[
            OpenApiParameter(
                "include_inactive",
                bool,
                description="Admins only: include sports awaiting setup after approval.",
            )
        ],
    ),
    retrieve=extend_schema(operation_id="sports_retrieve", summary="One sport, by slug"),
)
class SportViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = SportSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "slug"
    # The catalogue is a handful of rows and the client wants all of it at once.
    pagination_class = None

    def get_queryset(self):
        user = self.request.user
        is_admin = bool(
            getattr(user, "is_platform_admin", False) or getattr(user, "is_superuser", False)
        )
        requested = self.request.query_params.get("include_inactive") in {"1", "true", "True"}
        return sport_catalogue(include_inactive=is_admin and requested)


class AttributeListView(APIView):
    """The shared attributes, in display order."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="attributes_list",
        summary="Shared player attributes",
        responses={200: AttributeSerializer(many=True)},
    )
    def get(self, request):
        attributes = Attribute.objects.all()
        return Response(AttributeSerializer(attributes, many=True).data)


@extend_schema_view(
    list=extend_schema(operation_id="sport_proposals_list", summary="My sport proposals"),
    create=extend_schema(
        operation_id="sport_proposals_create",
        summary="Propose a sport",
        request=SportProposalCreateSerializer,
        responses={201: SportProposalSerializer},
    ),
)
class SportProposalViewSet(mixins.ListModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Anyone authenticated may propose for now; Phase 02 narrows this to turf owners."""

    serializer_class = SportProposalSerializer
    permission_classes = [IsAuthenticated]
    # Declared so drf-spectacular can infer the model without calling get_queryset()
    # with an AnonymousUser; the real queryset is per-request.
    queryset = SportProposal.objects.none()

    def get_queryset(self):
        return sport_proposals_for(self.request.user)

    def create(self, request, *args, **kwargs):
        payload = SportProposalCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            proposal = create_sport_proposal(
                user=request.user,
                name=payload.validated_data["name"],
                description=payload.validated_data.get("description", ""),
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(SportProposalSerializer(proposal).data, status=status.HTTP_201_CREATED)


@extend_schema_view(
    list=extend_schema(
        operation_id="admin_sport_proposals_list",
        summary="Sport proposal review queue",
        parameters=[OpenApiParameter("status", str, description="Filter by status.")],
    ),
    retrieve=extend_schema(
        operation_id="admin_sport_proposals_retrieve", summary="One sport proposal"
    ),
)
class AdminSportProposalViewSet(
    mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet
):
    serializer_class = SportProposalSerializer
    permission_classes = [IsPlatformAdmin]

    def get_queryset(self):
        return all_sport_proposals(status=self.request.query_params.get("status"))

    @extend_schema(
        operation_id="admin_sport_proposals_approve",
        summary="Approve a proposal (creates the sport)",
        request=SportProposalApproveSerializer,
        responses={200: SportSerializer},
    )
    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        proposal = self.get_object()
        payload = SportProposalApproveSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            sport = approve_sport_proposal(
                proposal=proposal,
                reviewer=request.user,
                name=payload.validated_data.get("name") or None,
                icon=payload.validated_data.get("icon", ""),
                met_value=payload.validated_data.get("met_value"),
                note=payload.validated_data.get("note", ""),
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(SportSerializer(sport).data)

    @extend_schema(
        operation_id="admin_sport_proposals_merge",
        summary="Merge a proposal into an existing sport",
        request=SportProposalMergeSerializer,
        responses={200: SportProposalSerializer},
    )
    @action(detail=True, methods=["post"])
    def merge(self, request, pk=None):
        proposal = self.get_object()
        payload = SportProposalMergeSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        sport = get_object_or_404(Sport, id=payload.validated_data["sport_id"])
        try:
            proposal = merge_sport_proposal(
                proposal=proposal,
                reviewer=request.user,
                sport=sport,
                note=payload.validated_data.get("note", ""),
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(SportProposalSerializer(proposal).data)

    @extend_schema(
        operation_id="admin_sport_proposals_reject",
        summary="Reject a proposal",
        request=SportProposalRejectSerializer,
        responses={200: SportProposalSerializer},
    )
    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        proposal = self.get_object()
        payload = SportProposalRejectSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            proposal = reject_sport_proposal(
                proposal=proposal,
                reviewer=request.user,
                note=payload.validated_data["note"],
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(SportProposalSerializer(proposal).data)
