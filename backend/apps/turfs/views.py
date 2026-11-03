from __future__ import annotations

from datetime import date as date_type

from django.contrib.gis.geos import Point
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsPlatformAdmin
from apps.core.utils import DHAKA, now

from .availability import get_availability, uncovered_minutes
from .models import (
    Amenity,
    Closure,
    Ground,
    OperatingHours,
    PriceRule,
    Turf,
    TurfMembership,
    TurfPhoto,
    Weekday,
)
from .permissions import IsTurfOwnerOrStaffReadOnly
from .selectors import (
    all_turfs_for_review,
    public_turfs,
    review_queue,
    search_turfs,
    turfs_for_staff,
)
from .serializers import (
    AmenitySerializer,
    AvailabilitySerializer,
    ClosureSerializer,
    GroundSerializer,
    GroundWriteSerializer,
    OperatingHoursSerializer,
    OwnerTurfSerializer,
    PriceCoverageGapSerializer,
    PriceRuleSerializer,
    ReviewDecisionSerializer,
    StaffInviteSerializer,
    TurfDetailSerializer,
    TurfMembershipSerializer,
    TurfPhotoSerializer,
    TurfSummarySerializer,
    TurfWriteSerializer,
)
from .services import (
    accept_staff_invite,
    activate_ground,
    approve_turf,
    create_ground,
    create_turf,
    deactivate_ground,
    invite_staff,
    reject_turf,
    remove_staff,
    submit_turf_for_review,
    suspend_turf,
)


def _drf_error(exc: DjangoValidationError) -> Response:
    detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
    return Response(detail, status=status.HTTP_400_BAD_REQUEST)


def _parse_point(raw: str | None) -> tuple[float, float] | None:
    """Parse ``near=lat,lng`` into PostGIS ``(longitude, latitude)`` order.

    Humans write latitude first; PostGIS takes longitude first. Swapping them silently
    puts Dhaka in the Indian Ocean, so the conversion happens exactly here.
    """
    if not raw:
        return None
    try:
        latitude, longitude = (float(part) for part in raw.split(",", 1))
    except (TypeError, ValueError) as exc:
        raise DjangoValidationError({"near": "Use `near=latitude,longitude`."}) from exc
    if not (-90 <= latitude <= 90) or not (-180 <= longitude <= 180):
        raise DjangoValidationError({"near": "Coordinates are out of range."})
    return (longitude, latitude)


def _parse_date(raw: str | None) -> date_type:
    """A Dhaka-local date; today when absent."""
    if not raw:
        return now().astimezone(DHAKA).date()
    try:
        return date_type.fromisoformat(raw)
    except ValueError as exc:
        raise DjangoValidationError({"date": "Use YYYY-MM-DD."}) from exc


# ---------------------------------------------------------------------------
# Public
# ---------------------------------------------------------------------------
@extend_schema_view(
    list=extend_schema(
        operation_id="turfs_list",
        summary="Find turfs",
        description=(
            "Approved turfs only. With `near` the results are annotated with "
            "`distance_km` and sorted nearest-first; without it, alphabetically, so the "
            "endpoint still works for a player who declines geolocation."
        ),
        parameters=[
            OpenApiParameter("near", str, description="`latitude,longitude`."),
            OpenApiParameter("radius_km", float, description="Only with `near`. Capped at 50."),
            OpenApiParameter("sport", str, description="Sport slug, e.g. `football`."),
            OpenApiParameter("area", str, description="Exact area, e.g. `Dhanmondi`."),
            OpenApiParameter("q", str, description="Free text over name, area and address."),
        ],
    ),
    retrieve=extend_schema(operation_id="turfs_retrieve", summary="One turf, by slug"),
)
class TurfViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    permission_classes = [IsAuthenticated]
    lookup_field = "slug"
    queryset = Turf.objects.none()

    def get_serializer_class(self):
        return TurfSummarySerializer if self.action == "list" else TurfDetailSerializer

    def get_queryset(self):
        if self.action != "list":
            return public_turfs()
        params = self.request.query_params
        return search_turfs(
            near=_parse_point(params.get("near")),
            radius_km=float(params["radius_km"]) if params.get("radius_km") else None,
            sport=params.get("sport"),
            area=params.get("area"),
            query=params.get("q"),
        )

    def list(self, request, *args, **kwargs):
        try:
            return super().list(request, *args, **kwargs)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        except ValueError:
            return Response({"radius_km": "Must be a number."}, status=status.HTTP_400_BAD_REQUEST)


class AmenityListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="amenities_list",
        summary="Amenities a turf can offer",
        responses={200: AmenitySerializer(many=True)},
    )
    def get(self, request):
        return Response(AmenitySerializer(Amenity.objects.all(), many=True).data)


class GroundAvailabilityView(APIView):
    """Slots for one ground on one Dhaka-local date (DOMAIN §4)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="ground_availability",
        summary="Slot availability for a ground",
        description=(
            "Operating hours minus closures minus active bookings, sliced by the "
            "ground's `slot_minutes`. Unavailable slots are included with a `reason` so "
            "the UI can grey them out rather than leave a gap."
        ),
        parameters=[OpenApiParameter("date", str, description="YYYY-MM-DD, Dhaka time.")],
        responses={200: AvailabilitySerializer},
    )
    def get(self, request, ground_id):
        # Only grounds at an approved turf: availability would otherwise leak the
        # existence of a venue still in review.
        ground = get_object_or_404(
            Ground.objects.select_related("turf").filter(
                is_active=True, turf__status=Turf.Status.APPROVED
            ),
            id=ground_id,
        )
        try:
            day = _parse_date(request.query_params.get("date"))
        except DjangoValidationError as exc:
            return _drf_error(exc)

        slots = get_availability(ground=ground, day=day)
        return Response(
            AvailabilitySerializer(
                {
                    "ground_id": ground.id,
                    "date": day,
                    "slot_minutes": ground.slot_minutes,
                    "slots": slots,
                }
            ).data
        )


# ---------------------------------------------------------------------------
# Owner
# ---------------------------------------------------------------------------
@extend_schema_view(
    list=extend_schema(operation_id="my_turfs_list", summary="Turfs I work at"),
    retrieve=extend_schema(operation_id="my_turfs_retrieve", summary="One of my turfs"),
    create=extend_schema(
        operation_id="my_turfs_create",
        summary="Register a turf",
        request=TurfWriteSerializer,
        responses={201: OwnerTurfSerializer},
    ),
    partial_update=extend_schema(
        operation_id="my_turfs_update",
        summary="Update one of my turfs",
        request=TurfWriteSerializer,
        responses={200: OwnerTurfSerializer},
    ),
)
class MyTurfViewSet(
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    mixins.CreateModelMixin,
    mixins.UpdateModelMixin,
    viewsets.GenericViewSet,
):
    """The owner's area. Authorisation is by membership, never by a user flag."""

    serializer_class = OwnerTurfSerializer
    permission_classes = [IsAuthenticated, IsTurfOwnerOrStaffReadOnly]
    lookup_field = "slug"
    queryset = Turf.objects.none()
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_queryset(self):
        return turfs_for_staff(self.request.user).prefetch_related("memberships")

    def create(self, request, *args, **kwargs):
        payload = TurfWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)
        amenities = data.pop("amenities", [])
        location = Point(data.pop("longitude"), data.pop("latitude"), srid=4326)

        try:
            turf = create_turf(owner=request.user, location=location, **data)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        if amenities:
            turf.amenities.set(amenities)

        return Response(
            self.get_serializer(self.get_queryset().get(pk=turf.pk)).data,
            status=status.HTTP_201_CREATED,
        )

    def partial_update(self, request, *args, **kwargs):
        turf = self.get_object()
        payload = TurfWriteSerializer(instance=turf, data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)

        amenities = data.pop("amenities", None)
        latitude = data.pop("latitude", None)
        longitude = data.pop("longitude", None)
        if latitude is not None and longitude is not None:
            turf.location = Point(longitude, latitude, srid=4326)

        for field, value in data.items():
            setattr(turf, field, value)
        turf.save()
        if amenities is not None:
            turf.amenities.set(amenities)

        return Response(self.get_serializer(self.get_queryset().get(pk=turf.pk)).data)

    @extend_schema(
        operation_id="my_turfs_submit",
        summary="Submit for review",
        request=None,
        responses={200: OwnerTurfSerializer},
    )
    @action(detail=True, methods=["post"])
    def submit(self, request, slug=None):
        turf = self.get_object()
        try:
            submit_turf_for_review(turf=turf)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(self.get_serializer(self.get_queryset().get(pk=turf.pk)).data)

    @extend_schema(
        operation_id="my_turfs_staff",
        summary="Staff at this turf",
        responses={200: TurfMembershipSerializer(many=True)},
    )
    @action(detail=True, methods=["get"], pagination_class=None)
    def staff(self, request, slug=None):
        turf = self.get_object()
        memberships = turf.memberships.exclude(status=TurfMembership.Status.REMOVED).select_related(
            "user", "turf"
        )
        return Response(TurfMembershipSerializer(memberships, many=True).data)

    @extend_schema(
        operation_id="my_turfs_invite_staff",
        summary="Invite staff",
        request=StaffInviteSerializer,
        responses={201: TurfMembershipSerializer},
    )
    @action(detail=True, methods=["post"], url_path="staff/invite")
    def invite(self, request, slug=None):
        turf = self.get_object()
        payload = StaffInviteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            membership = invite_staff(
                turf=turf,
                invited_by=request.user,
                role=payload.validated_data["role"],
                email=payload.validated_data.get("email", ""),
                phone=payload.validated_data.get("phone", ""),
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(TurfMembershipSerializer(membership).data, status=status.HTTP_201_CREATED)


class TurfSubResourceViewSet(viewsets.ModelViewSet):
    """Shared wiring for grounds, hours, closures, prices and photos.

    Each is scoped to one turf from the URL, and every one of them is owner-only — so
    the lookup, the permission check and the `turf` injection live here once instead of
    five times.
    """

    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_turf(self) -> Turf:
        turf = get_object_or_404(turfs_for_staff(self.request.user), slug=self.kwargs["slug"])
        # `IsTurfOwner` is an object permission, and the object here is the parent turf
        # rather than the row being written, so it is checked explicitly.
        self.check_object_permissions(self.request, turf)
        return turf

    def get_queryset(self):
        return self.model.objects.filter(turf=self.get_turf())

    def perform_create(self, serializer):
        serializer.save(turf=self.get_turf())


@extend_schema_view(
    list=extend_schema(operation_id="my_grounds_list", summary="Grounds at my turf"),
    create=extend_schema(
        operation_id="my_grounds_create",
        summary="Add a ground",
        request=GroundWriteSerializer,
        responses={201: GroundSerializer},
    ),
    partial_update=extend_schema(
        operation_id="my_grounds_update", summary="Update a ground", request=GroundWriteSerializer
    ),
    destroy=extend_schema(operation_id="my_grounds_delete", summary="Delete a ground"),
    retrieve=extend_schema(operation_id="my_grounds_retrieve", summary="One ground"),
)
class MyGroundViewSet(TurfSubResourceViewSet):
    model = Ground
    serializer_class = GroundSerializer
    permission_classes = [IsAuthenticated, IsTurfOwnerOrStaffReadOnly]
    queryset = Ground.objects.none()

    def get_queryset(self):
        return Ground.objects.filter(turf=self.get_turf()).prefetch_related(
            "sport_formats__sport", "price_rules"
        )

    def create(self, request, *args, **kwargs):
        turf = self.get_turf()
        payload = GroundWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            ground = create_ground(turf=turf, **payload.validated_data)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(GroundSerializer(ground).data, status=status.HTTP_201_CREATED)

    def partial_update(self, request, *args, **kwargs):
        ground = self.get_object()
        payload = GroundWriteSerializer(instance=ground, data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)
        sport_formats = data.pop("sport_formats", None)
        for field, value in data.items():
            setattr(ground, field, value)
        ground.save()
        if sport_formats is not None:
            ground.sport_formats.set(sport_formats)
        return Response(GroundSerializer(ground).data)

    @extend_schema(
        operation_id="my_grounds_activate",
        summary="Activate a ground",
        description=(
            "Refused until price rules cover every open minute (DOMAIN §4). The 400 lists the gaps."
        ),
        request=None,
        responses={200: GroundSerializer},
    )
    @action(detail=True, methods=["post"])
    def activate(self, request, slug=None, pk=None):
        ground = self.get_object()
        try:
            activate_ground(ground=ground)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(GroundSerializer(ground).data)

    @extend_schema(
        operation_id="my_grounds_deactivate",
        summary="Deactivate a ground",
        request=None,
        responses={200: GroundSerializer},
    )
    @action(detail=True, methods=["post"])
    def deactivate(self, request, slug=None, pk=None):
        ground = self.get_object()
        deactivate_ground(ground=ground)
        return Response(GroundSerializer(ground).data)

    @extend_schema(
        operation_id="my_grounds_price_coverage",
        summary="Open hours with no price",
        description="Empty means the ground can be activated.",
        responses={200: PriceCoverageGapSerializer(many=True)},
    )
    @action(detail=True, methods=["get"], url_path="price-coverage")
    def price_coverage(self, request, slug=None, pk=None):
        gaps = uncovered_minutes(ground=self.get_object())
        return Response(
            PriceCoverageGapSerializer(
                [
                    {
                        "weekday": weekday,
                        "weekday_label": Weekday(weekday).label,
                        "start_time": start,
                        "end_time": end,
                    }
                    for weekday, start, end in gaps
                ],
                many=True,
            ).data
        )


@extend_schema_view(
    list=extend_schema(operation_id="my_hours_list", summary="Opening hours"),
    create=extend_schema(operation_id="my_hours_create", summary="Add opening hours"),
    partial_update=extend_schema(operation_id="my_hours_update", summary="Update opening hours"),
    destroy=extend_schema(operation_id="my_hours_delete", summary="Delete opening hours"),
    retrieve=extend_schema(operation_id="my_hours_retrieve", summary="One opening-hours row"),
)
class MyOperatingHoursViewSet(TurfSubResourceViewSet):
    model = OperatingHours
    serializer_class = OperatingHoursSerializer
    permission_classes = [IsAuthenticated, IsTurfOwnerOrStaffReadOnly]
    queryset = OperatingHours.objects.none()


@extend_schema_view(
    list=extend_schema(operation_id="my_closures_list", summary="Closures"),
    create=extend_schema(operation_id="my_closures_create", summary="Add a closure"),
    partial_update=extend_schema(operation_id="my_closures_update", summary="Update a closure"),
    destroy=extend_schema(operation_id="my_closures_delete", summary="Delete a closure"),
    retrieve=extend_schema(operation_id="my_closures_retrieve", summary="One closure"),
)
class MyClosureViewSet(TurfSubResourceViewSet):
    model = Closure
    serializer_class = ClosureSerializer
    permission_classes = [IsAuthenticated, IsTurfOwnerOrStaffReadOnly]
    queryset = Closure.objects.none()


@extend_schema_view(
    list=extend_schema(operation_id="my_photos_list", summary="Turf photos"),
    create=extend_schema(operation_id="my_photos_create", summary="Upload a turf photo"),
    partial_update=extend_schema(operation_id="my_photos_update", summary="Update a photo"),
    destroy=extend_schema(operation_id="my_photos_delete", summary="Delete a photo"),
    retrieve=extend_schema(operation_id="my_photos_retrieve", summary="One photo"),
)
class MyTurfPhotoViewSet(TurfSubResourceViewSet):
    model = TurfPhoto
    serializer_class = TurfPhotoSerializer
    permission_classes = [IsAuthenticated, IsTurfOwnerOrStaffReadOnly]
    parser_classes = [MultiPartParser, FormParser, JSONParser]
    queryset = TurfPhoto.objects.none()


@extend_schema_view(
    list=extend_schema(operation_id="my_prices_list", summary="Price rules for a ground"),
    create=extend_schema(operation_id="my_prices_create", summary="Add a price rule"),
    partial_update=extend_schema(operation_id="my_prices_update", summary="Update a price rule"),
    destroy=extend_schema(operation_id="my_prices_delete", summary="Delete a price rule"),
    retrieve=extend_schema(operation_id="my_prices_retrieve", summary="One price rule"),
)
class MyPriceRuleViewSet(TurfSubResourceViewSet):
    """Price rules hang off a ground, which hangs off the turf in the URL."""

    model = PriceRule
    serializer_class = PriceRuleSerializer
    permission_classes = [IsAuthenticated, IsTurfOwnerOrStaffReadOnly]
    queryset = PriceRule.objects.none()

    def get_ground(self) -> Ground:
        return get_object_or_404(Ground, turf=self.get_turf(), pk=self.kwargs["ground_pk"])

    def get_queryset(self):
        return PriceRule.objects.filter(ground=self.get_ground())

    def perform_create(self, serializer):
        serializer.save(ground=self.get_ground())


class StaffMembershipViewSet(
    mixins.ListModelMixin, mixins.DestroyModelMixin, viewsets.GenericViewSet
):
    """My own staff invitations and memberships, across every turf."""

    serializer_class = TurfMembershipSerializer
    permission_classes = [IsAuthenticated]
    queryset = TurfMembership.objects.none()

    def get_queryset(self):
        user = self.request.user
        # Invitations sent to an email address that has no account yet still have to
        # reach the person once they sign up, hence the email match.
        return (
            (
                TurfMembership.objects.filter(user=user)
                | TurfMembership.objects.filter(
                    user__isnull=True, invited_email__iexact=(user.email or "\x00")
                )
            )
            .exclude(status=TurfMembership.Status.REMOVED)
            .select_related("turf", "user")
        )

    @extend_schema(operation_id="my_memberships_list", summary="My turf roles and invitations")
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        operation_id="my_memberships_accept",
        summary="Accept a staff invitation",
        request=None,
        responses={200: TurfMembershipSerializer},
    )
    @action(detail=True, methods=["post"])
    def accept(self, request, pk=None):
        membership = self.get_object()
        try:
            accept_staff_invite(membership=membership, user=request.user)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(TurfMembershipSerializer(membership).data)

    @extend_schema(operation_id="my_memberships_leave", summary="Leave a turf")
    def destroy(self, request, *args, **kwargs):
        membership = self.get_object()
        try:
            remove_staff(membership=membership)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


class TurfStaffRemoveView(APIView):
    """An owner removing someone from their turf."""

    permission_classes = [IsAuthenticated, IsTurfOwnerOrStaffReadOnly]

    @extend_schema(
        operation_id="my_turfs_remove_staff",
        summary="Remove a staff member",
        responses={204: None},
    )
    def delete(self, request, slug, membership_id):
        turf = get_object_or_404(turfs_for_staff(request.user), slug=slug)
        self.check_object_permissions(request, turf)
        membership = get_object_or_404(TurfMembership, turf=turf, id=membership_id)
        try:
            remove_staff(membership=membership)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
@extend_schema_view(
    list=extend_schema(
        operation_id="admin_turfs_list",
        summary="Turf review queue",
        parameters=[OpenApiParameter("status", str, description="Defaults to `pending_review`.")],
    ),
    retrieve=extend_schema(operation_id="admin_turfs_retrieve", summary="One turf under review"),
)
class AdminTurfViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = OwnerTurfSerializer
    permission_classes = [IsPlatformAdmin]
    lookup_field = "slug"
    queryset = Turf.objects.none()

    def get_queryset(self):
        # Reviewers see every ground, including inactive ones — an unpriced ground is
        # exactly the sort of thing a review should catch.
        requested = self.request.query_params.get("status")
        if self.action != "list":
            return all_turfs_for_review()
        if requested:
            return all_turfs_for_review().filter(status=requested)
        return review_queue()

    @extend_schema(
        operation_id="admin_turfs_approve",
        summary="Approve a turf",
        request=None,
        responses={200: OwnerTurfSerializer},
    )
    @action(detail=True, methods=["post"])
    def approve(self, request, slug=None):
        turf = self.get_object()
        try:
            approve_turf(turf=turf, reviewer=request.user)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(self.get_serializer(turf).data)

    @extend_schema(
        operation_id="admin_turfs_reject",
        summary="Reject a turf",
        request=ReviewDecisionSerializer,
        responses={200: OwnerTurfSerializer},
    )
    @action(detail=True, methods=["post"])
    def reject(self, request, slug=None):
        turf = self.get_object()
        payload = ReviewDecisionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            reject_turf(
                turf=turf, reviewer=request.user, reason=payload.validated_data.get("reason", "")
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(self.get_serializer(turf).data)

    @extend_schema(
        operation_id="admin_turfs_suspend",
        summary="Suspend a turf",
        request=ReviewDecisionSerializer,
        responses={200: OwnerTurfSerializer},
    )
    @action(detail=True, methods=["post"])
    def suspend(self, request, slug=None):
        turf = self.get_object()
        payload = ReviewDecisionSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            suspend_turf(
                turf=turf, reviewer=request.user, reason=payload.validated_data.get("reason", "")
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(self.get_serializer(turf).data)
