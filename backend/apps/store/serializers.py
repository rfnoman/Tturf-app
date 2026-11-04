from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.utils import player_label
from apps.inventory.serializers import NutritionSerializer, ProductSerializer

from .models import (
    Address,
    CartItem,
    DeliveryZone,
    Fulfilment,
    Order,
    OrderEvent,
    OrderItem,
    RiderProfile,
)


class DeliveryZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryZone
        fields = ["id", "name", "areas", "fee", "eta_hours", "is_active"]
        read_only_fields = fields


class AddressSerializer(serializers.ModelSerializer):
    class Meta:
        model = Address
        fields = ["id", "label", "line", "area", "phone", "is_default"]
        read_only_fields = ["id"]


class StoreMatchSerializer(serializers.Serializer):
    """The match the store arranges itself around."""

    id = serializers.UUIDField()
    sport = serializers.CharField()
    turf_name = serializers.CharField()
    turf_slug = serializers.SlugField()
    starts_at = serializers.DateTimeField()
    source_id = serializers.UUIDField(allow_null=True)


class StoreSourceSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    name = serializers.CharField()
    turf_slug = serializers.CharField(allow_blank=True)
    is_platform = serializers.BooleanField()


class StoreHomeSerializer(serializers.Serializer):
    """What the store's front page needs, typed so the client is too."""

    match = StoreMatchSerializer(allow_null=True)
    platform_source_id = serializers.UUIDField()
    sources = StoreSourceSerializer(many=True)


class StoreItemSerializer(serializers.Serializer):
    """One buyable thing at one source: the product, its price here, and how many."""

    stock_item_id = serializers.UUIDField(source="id")
    product = ProductSerializer()
    price = serializers.DecimalField(max_digits=12, decimal_places=2)
    available = serializers.IntegerField()
    source_id = serializers.UUIDField(source="location_id")
    source_name = serializers.CharField(source="location.name")
    turf_slug = serializers.SerializerMethodField()

    @extend_schema_field(serializers.CharField(allow_blank=True))
    def get_turf_slug(self, obj) -> str:
        return obj.location.turf.slug if obj.location.turf_id else ""


class CartItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(source="stock_item.product", read_only=True)
    stock_item_id = serializers.UUIDField(read_only=True)
    price = serializers.DecimalField(
        source="stock_item.price", max_digits=12, decimal_places=2, read_only=True
    )
    available = serializers.IntegerField(source="stock_item.available", read_only=True)
    line_total = serializers.SerializerMethodField()

    class Meta:
        model = CartItem
        fields = ["id", "stock_item_id", "product", "price", "quantity", "available", "line_total"]
        read_only_fields = fields

    @extend_schema_field(serializers.DecimalField(max_digits=12, decimal_places=2))
    def get_line_total(self, obj):
        return obj.stock_item.price * obj.quantity


class FulfilmentOptionSerializer(serializers.Serializer):
    """An option, and — when it is closed — why."""

    kind = serializers.ChoiceField(choices=Fulfilment.choices)
    available = serializers.BooleanField()
    fee = serializers.DecimalField(max_digits=12, decimal_places=2)
    eta_hours = serializers.IntegerField(allow_null=True)
    reason = serializers.CharField(allow_blank=True)


class CartGroupSerializer(serializers.Serializer):
    """The cart as it will be ordered: one group per source, with its own options."""

    source_id = serializers.UUIDField()
    source_name = serializers.CharField()
    turf_slug = serializers.CharField(allow_blank=True)
    is_platform = serializers.BooleanField()
    items = CartItemSerializer(many=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2)
    options = FulfilmentOptionSerializer(many=True)


class CartSerializer(serializers.Serializer):
    groups = CartGroupSerializer(many=True)
    subtotal = serializers.DecimalField(max_digits=12, decimal_places=2)
    item_count = serializers.IntegerField()


class AddToCartSerializer(serializers.Serializer):
    stock_item_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, default=1)


class SetCartQuantitySerializer(serializers.Serializer):
    stock_item_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=0)


class CheckoutChoiceSerializer(serializers.Serializer):
    source_id = serializers.UUIDField()
    fulfilment = serializers.ChoiceField(choices=Fulfilment.choices)
    match_id = serializers.UUIDField(required=False, allow_null=True)
    address_id = serializers.UUIDField(required=False, allow_null=True)
    notes = serializers.CharField(max_length=300, required=False, allow_blank=True)


class CheckoutSerializer(serializers.Serializer):
    choices = CheckoutChoiceSerializer(many=True)


class OrderItemSerializer(serializers.ModelSerializer):
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    # Declared rather than left as a bare JSONField: the snapshot always has this shape,
    # and a client typed against `{}` cannot read it.
    nutrition = NutritionSerializer(read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "name", "unit_price", "quantity", "line_total", "nutrition"]
        read_only_fields = fields


class OrderEventSerializer(serializers.ModelSerializer):
    to_status_label = serializers.CharField(source="get_to_status_display", read_only=True)
    actor_name = serializers.SerializerMethodField()

    class Meta:
        model = OrderEvent
        fields = [
            "id",
            "from_status",
            "to_status",
            "to_status_label",
            "actor_name",
            "note",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_blank=True))
    def get_actor_name(self, obj) -> str:
        if not obj.actor:
            return ""
        return player_label(obj.actor)


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)
    events = OrderEventSerializer(many=True, read_only=True)
    source_name = serializers.CharField(source="location.name", read_only=True)
    turf_slug = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    fulfilment_label = serializers.CharField(source="get_fulfilment_display", read_only=True)
    player_name = serializers.SerializerMethodField()
    rider_name = serializers.SerializerMethodField()
    address = AddressSerializer(read_only=True)
    match_summary = serializers.SerializerMethodField()

    class Meta:
        model = Order
        fields = [
            "id",
            "source_name",
            "turf_slug",
            "player_name",
            "fulfilment",
            "fulfilment_label",
            "status",
            "status_label",
            "subtotal",
            "delivery_fee",
            "total",
            "payment_method",
            "address",
            "match",
            "match_summary",
            "rider_name",
            "scheduled_for",
            "notes",
            "settled_at",
            "cancel_reason",
            "items",
            "events",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_blank=True))
    def get_turf_slug(self, obj) -> str:
        return obj.location.turf.slug if obj.location.turf_id else ""

    @extend_schema_field(serializers.CharField())
    def get_player_name(self, obj) -> str:
        return player_label(obj.player)

    @extend_schema_field(serializers.CharField(allow_blank=True))
    def get_rider_name(self, obj) -> str:
        return str(obj.rider) if obj.rider_id else ""

    @extend_schema_field(serializers.CharField(allow_blank=True))
    def get_match_summary(self, obj) -> str:
        if not obj.match_id:
            return ""
        return f"{obj.match.sport.display_name} at {obj.match.turf.name}"


class RiderSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()

    class Meta:
        model = RiderProfile
        fields = ["id", "name", "phone", "is_active"]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_name(self, obj) -> str:
        return str(obj)


class AssignRiderSerializer(serializers.Serializer):
    rider_id = serializers.UUIDField()


class CancelOrderSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True)


class SettleOrderSerializer(serializers.Serializer):
    cash_received = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, min_value=0
    )
