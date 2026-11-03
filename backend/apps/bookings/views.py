from __future__ import annotations

from datetime import date as date_type

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.utils import DHAKA, now
from apps.sports.models import SportFormat
from apps.turfs.models import Ground
from apps.turfs.selectors import turfs_for_staff

from .models import Booking
from .permissions import CanViewBooking, IsBookingTurfStaff
from .selectors import (
    bookings_for_turf,
    bookings_visible_to,
    past_for_player,
    pending_confirmation_for_turf,
    upcoming_for_player,
)
from .serializers import (
    BookingCreateSerializer,
    BookingSerializer,
    CancelBookingSerializer,
    MarkPaidSerializer,
    NoteSerializer,
    WalkInBookingSerializer,
)
from .services import (
    SlotTakenError,
    cancel_booking,
    confirm_booking,
    create_booking,
    mark_no_show,
    mark_paid,
)


def _drf_error(exc: DjangoValidationError, *, code=status.HTTP_400_BAD_REQUEST) -> Response:
    detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
    return Response(detail, status=code)


def _parse_date(raw: str | None) -> date_type:
    if not raw:
        return now().astimezone(DHAKA).date()
    try:
        return date_type.fromisoformat(raw)
    except ValueError as exc:
        raise DjangoValidationError({"date": "Use YYYY-MM-DD."}) from exc


@extend_schema_view(
    retrieve=extend_schema(
        operation_id="bookings_retrieve",
        summary="One booking",
        description="Visible to the player who booked it and to staff at that turf.",
    ),
)
class BookingViewSet(mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """A single booking and everything that can be done to it."""

    serializer_class = BookingSerializer
    permission_classes = [IsAuthenticated, CanViewBooking]
    queryset = Booking.objects.none()

    def get_queryset(self):
        return bookings_visible_to(self.request.user)

    def _run(self, service, **kwargs) -> Response:
        booking = self.get_object()
        try:
            service(booking=booking, **kwargs)
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(BookingSerializer(self.get_queryset().get(pk=booking.pk)).data)

    @extend_schema(
        operation_id="bookings_create",
        summary="Book a slot",
        description=(
            "Applies DECISIONS D3: a reliable player at a turf that allows it is "
            "confirmed immediately, otherwise the slot is held until `expires_at`. "
            "Returns **409** when another player took the slot first."
        ),
        request=BookingCreateSerializer,
        responses={201: BookingSerializer, 409: BookingCreateSerializer},
    )
    def create(self, request, *args, **kwargs):
        payload = BookingCreateSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        ground = get_object_or_404(Ground.objects.select_related("turf"), id=data["ground_id"])
        sport_format = get_object_or_404(SportFormat, id=data["sport_format_id"])

        try:
            booking = create_booking(
                user=request.user,
                ground=ground,
                start=data["start"],
                sport_format=sport_format,
                mode=data.get("mode") or "individual",
                visibility=data.get("visibility") or "public",
                notes=data.get("notes", ""),
            )
        except SlotTakenError as exc:
            # 409, not 400: nothing the client sent was wrong, somebody was simply faster.
            return _drf_error(exc, code=status.HTTP_409_CONFLICT)
        except DjangoValidationError as exc:
            return _drf_error(exc)

        return Response(
            BookingSerializer(self.get_queryset().get(pk=booking.pk)).data,
            status=status.HTTP_201_CREATED,
        )

    @extend_schema(
        operation_id="bookings_cancel",
        summary="Cancel a booking",
        description=(
            "A player cancelling inside the turf's free window takes a reliability hit; "
            "a cancellation by the turf does not."
        ),
        request=CancelBookingSerializer,
        responses={200: BookingSerializer},
    )
    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        booking = self.get_object()
        payload = CancelBookingSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        from .permissions import is_turf_staff

        by_staff = is_turf_staff(booking=booking, user=request.user)
        try:
            cancel_booking(
                booking=booking,
                actor=request.user,
                reason=payload.validated_data.get("reason", ""),
                by_staff=by_staff,
            )
        except DjangoValidationError as exc:
            return _drf_error(exc)
        return Response(BookingSerializer(self.get_queryset().get(pk=booking.pk)).data)

    @extend_schema(
        operation_id="bookings_confirm",
        summary="Confirm a booking (staff)",
        request=NoteSerializer,
        responses={200: BookingSerializer},
    )
    @action(detail=True, methods=["post"], permission_classes=[IsAuthenticated, IsBookingTurfStaff])
    def confirm(self, request, pk=None):
        payload = NoteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self._run(
            confirm_booking, actor=request.user, note=payload.validated_data.get("note", "")
        )

    @extend_schema(
        operation_id="bookings_mark_paid",
        summary="Record cash payment (staff)",
        request=MarkPaidSerializer,
        responses={200: BookingSerializer},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="mark-paid",
        permission_classes=[IsAuthenticated, IsBookingTurfStaff],
    )
    def mark_paid(self, request, pk=None):
        payload = MarkPaidSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self._run(mark_paid, actor=request.user, amount=payload.validated_data.get("amount"))

    @extend_schema(
        operation_id="bookings_no_show",
        summary="Mark a no-show (staff)",
        description=(
            "Refused until the grace period after kickoff has passed — a player stuck "
            "in traffic three minutes away is not a no-show."
        ),
        request=NoteSerializer,
        responses={200: BookingSerializer},
    )
    @action(
        detail=True,
        methods=["post"],
        url_path="no-show",
        permission_classes=[IsAuthenticated, IsBookingTurfStaff],
    )
    def no_show(self, request, pk=None):
        payload = NoteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self._run(
            mark_no_show, actor=request.user, note=payload.validated_data.get("note", "")
        )


class MyBookingsView(APIView):
    """The player's own bookings, split the way the UI shows them."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="my_bookings_list",
        summary="My bookings",
        parameters=[OpenApiParameter("filter", str, description="`upcoming` (default) or `past`.")],
        responses={200: BookingSerializer(many=True)},
    )
    def get(self, request):
        which = request.query_params.get("filter", "upcoming")
        queryset = (
            past_for_player(request.user) if which == "past" else upcoming_for_player(request.user)
        )
        return Response(BookingSerializer(queryset, many=True).data)


class TurfBookingsView(APIView):
    """The owner/staff calendar for one turf."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="turf_bookings_list",
        summary="Bookings at my turf",
        parameters=[
            OpenApiParameter("date", str, description="YYYY-MM-DD, Dhaka time. Defaults to today."),
            OpenApiParameter("status", str, description="Filter by booking status."),
        ],
        responses={200: BookingSerializer(many=True)},
    )
    def get(self, request, slug):
        # Scoped to turfs this user actually staffs, so there is no cross-turf read.
        turf = get_object_or_404(turfs_for_staff(request.user), slug=slug)
        try:
            day = _parse_date(request.query_params.get("date"))
        except DjangoValidationError as exc:
            return _drf_error(exc)

        queryset = bookings_for_turf(turf, day=day, status=request.query_params.get("status"))
        return Response(BookingSerializer(queryset, many=True).data)


class TurfPendingBookingsView(APIView):
    """The confirmation queue, soonest deadline first (DECISIONS D3)."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="turf_bookings_pending",
        summary="Bookings awaiting confirmation",
        responses={200: BookingSerializer(many=True)},
    )
    def get(self, request, slug):
        turf = get_object_or_404(turfs_for_staff(request.user), slug=slug)
        return Response(BookingSerializer(pending_confirmation_for_turf(turf), many=True).data)


class WalkInBookingView(APIView):
    """Staff taking a booking at the counter for someone with no account."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="turf_bookings_walk_in",
        summary="Book on behalf of a walk-in (staff)",
        description=(
            "Recorded against the staff member's account with the customer's name and "
            "phone, and confirmed immediately — they are standing at the counter."
        ),
        request=WalkInBookingSerializer,
        responses={201: BookingSerializer, 409: WalkInBookingSerializer},
    )
    def post(self, request, slug):
        turf = get_object_or_404(turfs_for_staff(request.user), slug=slug)
        payload = WalkInBookingSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        ground = get_object_or_404(
            Ground.objects.select_related("turf"), id=data["ground_id"], turf=turf
        )
        sport_format = get_object_or_404(SportFormat, id=data["sport_format_id"])

        try:
            booking = create_booking(
                user=request.user,
                ground=ground,
                start=data["start"],
                sport_format=sport_format,
                mode=data.get("mode") or "individual",
                visibility="private",
                notes=data.get("notes", ""),
                booked_for_name=data["booked_for_name"],
                booked_for_phone=data.get("booked_for_phone", ""),
            )
            # Somebody is standing at the counter with cash; there is nothing to confirm.
            if booking.status == "reserved":
                confirm_booking(booking=booking, actor=request.user, note="Walk-in at the counter")
        except SlotTakenError as exc:
            return _drf_error(exc, code=status.HTTP_409_CONFLICT)
        except DjangoValidationError as exc:
            return _drf_error(exc)

        return Response(
            BookingSerializer(bookings_visible_to(request.user).get(pk=booking.pk)).data,
            status=status.HTTP_201_CREATED,
        )
