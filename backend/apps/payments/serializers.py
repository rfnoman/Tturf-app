from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import LedgerEntry, Payment, PaymentKind, PaymentMethod, Payout, Refund


class PaymentSerializer(serializers.ModelSerializer):
    collected_by_name = serializers.CharField(
        source="collected_by.full_name", read_only=True, default=""
    )
    method_label = serializers.CharField(source="get_method_display", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "method",
            "method_label",
            "kind",
            "amount",
            "status",
            "collected_by_name",
            "collected_at",
            "reference",
            "note",
            "created_at",
        ]
        read_only_fields = fields


class PaymentDetailSerializer(PaymentSerializer):
    """What a player sees about one payment, including where to pay it.

    `redirect_url` is included; `raw_response` is not. The gateway's reply is for
    reconciliation and disputes, not for the browser.
    """

    status_label = serializers.CharField(source="get_status_display", read_only=True)
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    what_for = serializers.SerializerMethodField()
    refunded = serializers.SerializerMethodField()

    class Meta(PaymentSerializer.Meta):
        fields = [
            *PaymentSerializer.Meta.fields,
            "status_label",
            "kind_label",
            "what_for",
            "refunded",
            "redirect_url",
            "booking",
            "order",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_what_for(self, obj) -> str:
        if obj.booking_id:
            return f"{obj.booking.ground.turf.name} · {obj.booking.ground.name}"
        if obj.order_id:
            return f"Order from {obj.order.location.name}"
        return ""

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_refunded(self, obj):
        return obj.refunded_amount


class StartPaymentSerializer(serializers.Serializer):
    """Pay for a booking or an order."""

    booking_id = serializers.UUIDField(required=False, allow_null=True)
    order_id = serializers.UUIDField(required=False, allow_null=True)
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    kind = serializers.ChoiceField(choices=PaymentKind.choices, default=PaymentKind.FULL)

    def validate(self, data):
        if bool(data.get("booking_id")) == bool(data.get("order_id")):
            raise serializers.ValidationError(
                {"booking_id": "Name exactly one of a booking or an order."}
            )
        return data


class RefundSerializer(serializers.ModelSerializer):
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Refund
        fields = [
            "id",
            "payment",
            "amount",
            "reason",
            "status",
            "status_label",
            "provider_ref",
            "settled_at",
            "created_at",
        ]
        read_only_fields = fields


class RefundPolicySerializer(serializers.Serializer):
    """What a cancellation would be worth back, before anybody commits to it."""

    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    reason = serializers.CharField()
    forfeits_advance = serializers.BooleanField()


class LedgerEntrySerializer(serializers.ModelSerializer):
    account_label = serializers.CharField(source="get_account_display", read_only=True)
    type_label = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = LedgerEntry
        fields = [
            "id",
            "occurred_on",
            "account",
            "account_label",
            "type",
            "type_label",
            "amount",
            "note",
        ]
        read_only_fields = fields


class PayoutSerializer(serializers.ModelSerializer):
    turf_name = serializers.CharField(source="turf.name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Payout
        fields = [
            "id",
            "turf",
            "turf_name",
            "period_start",
            "period_end",
            "amount",
            "status",
            "status_label",
            "reference",
            "sent_at",
            "note",
        ]
        read_only_fields = fields


class StatementSerializer(serializers.Serializer):
    """A turf's earnings for a period, and the lines behind the number."""

    period_start = serializers.DateField()
    period_end = serializers.DateField()
    total = serializers.DecimalField(max_digits=12, decimal_places=2)
    already_paid = serializers.DecimalField(max_digits=12, decimal_places=2)
    by_type = serializers.DictField(child=serializers.DecimalField(max_digits=12, decimal_places=2))
    entries = LedgerEntrySerializer(many=True)


class MarkPayoutSentSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=120, required=False, allow_blank=True)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)


class CreatePayoutSerializer(serializers.Serializer):
    turf = serializers.SlugField()
    period_start = serializers.DateField()
    period_end = serializers.DateField()


class PlatformFinanceSerializer(serializers.Serializer):
    """The platform's own position for a period."""

    period_start = serializers.DateField()
    period_end = serializers.DateField()
    platform = serializers.DecimalField(max_digits=12, decimal_places=2)
    delivery = serializers.DecimalField(max_digits=12, decimal_places=2)
    owed_to_turfs = serializers.DecimalField(max_digits=12, decimal_places=2)
    payments = serializers.IntegerField()
    refunds = serializers.IntegerField()
