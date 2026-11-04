"""Payment endpoints: starting one, hearing back, and the money screens.

The IPN endpoint is the only unauthenticated write in the app. It is safe because it
decides nothing: it looks a payment up, asks the provider directly what happened, and
acts on that answer. A forged post reaches a validation call that says no.
"""

from __future__ import annotations

import logging
from datetime import date as date_type

from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bookings.models import Booking
from apps.core.permissions import IsPlatformAdmin
from apps.core.utils import now, to_dhaka
from apps.store.models import Order
from apps.turfs.models import Turf
from apps.turfs.selectors import turfs_for_staff
from apps.turfs.services import TURF_EDIT_ROLES, has_turf_role

from .ledger import balance_for
from .models import LedgerAccount, Payment, PaymentStatus, Payout, Refund
from .serializers import (
    CreatePayoutSerializer,
    MarkPayoutSentSerializer,
    PaymentDetailSerializer,
    PayoutSerializer,
    PlatformFinanceSerializer,
    RefundPolicySerializer,
    RefundSerializer,
    StartPaymentSerializer,
    StatementSerializer,
)
from .services import (
    create_payout,
    mark_payout_sent,
    payout_statement,
    refund_booking,
    refund_due,
    settle_payment,
    start_online_payment,
)

logger = logging.getLogger(__name__)


def _error(exc: DjangoValidationError) -> Response:
    detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
    return Response(detail, status=status.HTTP_400_BAD_REQUEST)


def _period(request) -> tuple[date_type, date_type]:
    """The window a finance screen is asking about. Defaults to this month."""
    today = to_dhaka(now()).date()
    try:
        since = date_type.fromisoformat(request.query_params["from"])
    except KeyError, ValueError:
        since = today.replace(day=1)
    try:
        until = date_type.fromisoformat(request.query_params["to"])
    except KeyError, ValueError:
        until = today
    return since, until


class StartPaymentView(APIView):
    """Begin paying for a booking or an order."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="payment_start",
        summary="Start a payment",
        request=StartPaymentSerializer,
        responses={201: PaymentDetailSerializer},
    )
    def post(self, request):
        payload = StartPaymentSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        if data.get("booking_id"):
            target = get_object_or_404(
                Booking.objects.select_related("ground__turf"),
                id=data["booking_id"],
                booked_by=request.user,
            )
        else:
            target = get_object_or_404(
                Order.objects.select_related("location"),
                id=data["order_id"],
                player=request.user,
            )

        try:
            payment = start_online_payment(
                target=target,
                method=data["method"],
                kind=data["kind"],
                actor=request.user,
            )
        except DjangoValidationError as exc:
            return _error(exc)

        return Response(PaymentDetailSerializer(payment).data, status=status.HTTP_201_CREATED)


class PaymentDetailView(APIView):
    """One payment, for the person who made it."""

    permission_classes = [IsAuthenticated]

    def _payment(self, request, payment_id) -> Payment:
        payment = get_object_or_404(
            Payment.objects.select_related("booking__ground__turf", "order__location"),
            id=payment_id,
        )
        target = payment.target
        owner = getattr(target, "booked_by_id", None) or getattr(target, "player_id", None)
        if owner != request.user.id and not getattr(request.user, "is_platform_admin", False):
            self.permission_denied(request, message="No such payment.")
        return payment

    @extend_schema(
        operation_id="payment_detail",
        summary="One payment",
        parameters=[
            OpenApiParameter(
                "val_id",
                str,
                description="The gateway's validation id, when the player has just come back.",
            )
        ],
        responses={200: PaymentDetailSerializer},
    )
    def get(self, request, payment_id):
        payment = self._payment(request, payment_id)

        # A player landing back from the gateway usually arrives before the IPN does,
        # so the result page asks the provider itself rather than showing "pending" and
        # hoping. Settling is idempotent, so doing it here is free.
        if payment.status == PaymentStatus.PENDING and payment.method != "cash":
            try:
                payment = settle_payment(
                    payment=payment,
                    callback={"val_id": request.query_params.get("val_id", "")},
                    actor=request.user,
                )
            except DjangoValidationError:
                logger.info("Could not settle on return", extra={"payment": str(payment.id)})

        return Response(PaymentDetailSerializer(payment).data)


@method_decorator(csrf_exempt, name="dispatch")
class PaymentIpnView(APIView):
    """Where a gateway posts what it thinks happened.

    Unauthenticated because a gateway has no session, and **safe for the same reason it
    is unauthenticated**: the body is treated as a hint. The payment is found by our own
    transaction id, and the provider is then asked directly. A forged post gets a
    validation call that says no, and nothing moves.
    """

    authentication_classes: list = []
    permission_classes = [AllowAny]

    @extend_schema(exclude=True)
    def post(self, request, provider: str):
        data = request.data if isinstance(request.data, dict) else {}
        reference = data.get("tran_id") or data.get("value_a") or ""

        payment = Payment.objects.filter(provider_txn_id=reference).first()
        if payment is None and reference:
            # `value_a` carries our payment id, which is how a gateway that mangles
            # `tran_id` can still be matched. A non-UUID there is somebody probing.
            from uuid import UUID

            try:
                payment = Payment.objects.filter(id=UUID(str(reference))).first()
            except ValueError, AttributeError, TypeError:
                payment = None

        if payment is None:
            # 200 on purpose: a gateway that gets an error retries for hours, and there
            # is nothing to retry here. The log line is what matters.
            logger.warning("IPN for an unknown payment", extra={"provider": provider})
            return HttpResponse("unknown", content_type="text/plain")

        try:
            settle_payment(payment=payment, callback=data)
        except DjangoValidationError:
            logger.warning("IPN could not be settled", extra={"payment": str(payment.id)})
            return HttpResponse("retry", content_type="text/plain", status=503)

        return HttpResponse("ok", content_type="text/plain")


class MyPaymentsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="my_payments",
        summary="My payments",
        responses={200: PaymentDetailSerializer(many=True)},
    )
    def get(self, request):
        payments = (
            Payment.objects.filter(
                Q(booking__booked_by=request.user) | Q(order__player=request.user)
            )
            .select_related("booking__ground__turf", "order__location")
            .prefetch_related("refunds")
            .order_by("-created_at")[:100]
        )
        return Response(PaymentDetailSerializer(payments, many=True).data)


class BookingRefundQuoteView(APIView):
    """What cancelling would be worth back, before anybody commits."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="refund_quote",
        summary="What a cancellation refunds",
        responses={200: RefundPolicySerializer},
    )
    def get(self, request, booking_id):
        booking = get_object_or_404(Booking.objects.select_related("ground__turf"), id=booking_id)
        is_player = booking.booked_by_id == request.user.id
        is_staff = has_turf_role(turf=booking.ground.turf, user=request.user, roles=TURF_EDIT_ROLES)
        if not (is_player or is_staff):
            self.permission_denied(request, message="No such booking.")

        policy = refund_due(booking=booking, cancelled_by_turf=is_staff and not is_player)
        return Response(
            RefundPolicySerializer(
                {
                    "amount": policy.amount,
                    "reason": policy.reason,
                    "forfeits_advance": policy.forfeits_advance,
                }
            ).data
        )


class TurfFinanceView(APIView):
    """What a turf has earned, and what it is owed."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="turf_finance",
        summary="A turf's earnings",
        parameters=[
            OpenApiParameter("from", str, description="YYYY-MM-DD. Default: this month."),
            OpenApiParameter("to", str),
        ],
        responses={200: StatementSerializer},
    )
    def get(self, request, slug):
        turf = get_object_or_404(turfs_for_staff(request.user), slug=slug)
        if not has_turf_role(turf=turf, user=request.user, roles=TURF_EDIT_ROLES):
            self.permission_denied(request, message="Only an owner can see the money.")

        since, until = _period(request)
        statement = payout_statement(turf=turf, since=since, until=until)
        return Response(StatementSerializer(statement).data)


class TurfPayoutListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="turf_payouts",
        summary="A turf's payouts",
        responses={200: PayoutSerializer(many=True)},
    )
    def get(self, request, slug):
        turf = get_object_or_404(turfs_for_staff(request.user), slug=slug)
        if not has_turf_role(turf=turf, user=request.user, roles=TURF_EDIT_ROLES):
            self.permission_denied(request, message="Only an owner can see the money.")
        return Response(PayoutSerializer(turf.payouts.all()[:50], many=True).data)


class AdminFinanceView(APIView):
    """The platform's own position."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    @extend_schema(
        operation_id="admin_finance",
        summary="Platform finance",
        parameters=[OpenApiParameter("from", str), OpenApiParameter("to", str)],
        responses={200: PlatformFinanceSerializer},
    )
    def get(self, request):
        since, until = _period(request)
        return Response(
            PlatformFinanceSerializer(
                {
                    "period_start": since,
                    "period_end": until,
                    "platform": balance_for(
                        account=LedgerAccount.PLATFORM, since=since, until=until
                    ),
                    "delivery": balance_for(
                        account=LedgerAccount.DELIVERY, since=since, until=until
                    ),
                    "owed_to_turfs": balance_for(account=LedgerAccount.TURF),
                    "payments": Payment.objects.filter(
                        status=PaymentStatus.PAID, collected_at__date__gte=since
                    ).count(),
                    "refunds": Refund.objects.filter(
                        status=Refund.Status.DONE, settled_at__date__gte=since
                    ).count(),
                }
            ).data
        )


class AdminRefundListView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    @extend_schema(
        operation_id="admin_refunds",
        summary="Refunds",
        responses={200: RefundSerializer(many=True)},
    )
    def get(self, request):
        return Response(
            RefundSerializer(
                Refund.objects.select_related("payment").order_by("-created_at")[:100], many=True
            ).data
        )


class AdminBookingRefundView(APIView):
    """Refund a booking by policy, for support cases."""

    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    @extend_schema(
        operation_id="admin_refund_booking",
        summary="Refund a booking",
        request=None,
        responses={200: RefundSerializer(many=True)},
    )
    def post(self, request, booking_id):
        booking = get_object_or_404(Booking.objects.select_related("ground__turf"), id=booking_id)
        refunds = refund_booking(booking=booking, actor=request.user, cancelled_by_turf=True)
        return Response(RefundSerializer(refunds, many=True).data)


class AdminPayoutView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    @extend_schema(
        operation_id="admin_payouts",
        summary="Payouts",
        responses={200: PayoutSerializer(many=True)},
    )
    def get(self, request):
        return Response(
            PayoutSerializer(
                Payout.objects.select_related("turf").order_by("-period_end")[:100], many=True
            ).data
        )

    @extend_schema(
        operation_id="admin_payout_create",
        summary="Draft a payout",
        request=CreatePayoutSerializer,
        responses={201: PayoutSerializer},
    )
    def post(self, request):
        payload = CreatePayoutSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        turf = get_object_or_404(Turf, slug=payload.validated_data["turf"])

        try:
            payout = create_payout(
                turf=turf,
                since=payload.validated_data["period_start"],
                until=payload.validated_data["period_end"],
                actor=request.user,
            )
        except DjangoValidationError as exc:
            return _error(exc)

        return Response(PayoutSerializer(payout).data, status=status.HTTP_201_CREATED)


class AdminPayoutSendView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    @extend_schema(
        operation_id="admin_payout_send",
        summary="Record a payout as sent",
        request=MarkPayoutSentSerializer,
        responses={200: PayoutSerializer},
    )
    def post(self, request, payout_id):
        payout = get_object_or_404(Payout.objects.select_related("turf"), id=payout_id)
        payload = MarkPayoutSentSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        try:
            payout = mark_payout_sent(
                payout=payout,
                actor=request.user,
                reference=payload.validated_data.get("reference", ""),
                note=payload.validated_data.get("note", ""),
            )
        except DjangoValidationError as exc:
            return _error(exc)

        return Response(PayoutSerializer(payout).data)


class TurfStatementCsvView(APIView):
    """The statement as a file, because an owner's accountant wants one."""

    permission_classes = [IsAuthenticated]

    @extend_schema(exclude=True)
    def get(self, request, slug):
        import csv
        from io import StringIO

        turf = get_object_or_404(turfs_for_staff(request.user), slug=slug)
        if not has_turf_role(turf=turf, user=request.user, roles=TURF_EDIT_ROLES):
            self.permission_denied(request, message="Only an owner can see the money.")

        since, until = _period(request)
        statement = payout_statement(turf=turf, since=since, until=until)

        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Date", "Type", "Amount (BDT)", "Note"])
        for entry in statement["entries"]:
            writer.writerow([entry.occurred_on, entry.get_type_display(), entry.amount, entry.note])
        writer.writerow([])
        writer.writerow(["Total", "", statement["total"], ""])

        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="{turf.slug}-{since}-{until}.csv"'
        return response
