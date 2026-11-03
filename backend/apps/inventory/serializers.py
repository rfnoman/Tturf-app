from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import (
    CounterSale,
    CounterSaleLine,
    MovementType,
    Product,
    ProductCategory,
    ProductKind,
    Rental,
    StockItem,
    StockMovement,
)


class ProductCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductCategory
        fields = ["id", "slug", "label", "icon", "order", "is_consumable"]
        read_only_fields = fields


class NutritionSerializer(serializers.Serializer):
    """The nutrition panel, kept together so the UI can hide it in one go."""

    serving_size = serializers.CharField(allow_blank=True)
    calories = serializers.IntegerField(allow_null=True)
    protein_g = serializers.DecimalField(max_digits=6, decimal_places=1, allow_null=True)
    carbs_g = serializers.DecimalField(max_digits=6, decimal_places=1, allow_null=True)
    fat_g = serializers.DecimalField(max_digits=6, decimal_places=1, allow_null=True)
    sugar_g = serializers.DecimalField(max_digits=6, decimal_places=1, allow_null=True)
    caffeine_mg = serializers.IntegerField(allow_null=True)


class ProductSerializer(serializers.ModelSerializer):
    """A product as everybody reads it, with its nutrition grouped."""

    category = ProductCategorySerializer(read_only=True)
    nutrition = serializers.SerializerMethodField()
    tags = serializers.ListField(child=serializers.CharField(), read_only=True)
    sports = serializers.SerializerMethodField()
    turf_name = serializers.CharField(source="turf.name", read_only=True, allow_null=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "owner_type",
            "turf",
            "turf_name",
            "category",
            "name",
            "slug",
            "description",
            "image_url",
            "kind",
            "base_price",
            "rental_price_per_match",
            "deposit",
            "perishable",
            "sku",
            "barcode",
            "nutrition",
            "tags",
            "sports",
            "is_active",
        ]
        read_only_fields = fields

    @extend_schema_field(NutritionSerializer)
    def get_nutrition(self, obj) -> dict:
        return {
            "serving_size": obj.serving_size,
            "calories": obj.calories,
            "protein_g": obj.protein_g,
            "carbs_g": obj.carbs_g,
            "fat_g": obj.fat_g,
            "sugar_g": obj.sugar_g,
            "caffeine_mg": obj.caffeine_mg,
        }

    @extend_schema_field(serializers.ListField(child=serializers.CharField()))
    def get_sports(self, obj) -> list[str]:
        return [sport.slug for sport in obj.sports.all()]


class ProductWriteSerializer(serializers.ModelSerializer):
    """What an owner may set. `owner_type` and `turf` come from the URL, never the body."""

    category = serializers.SlugRelatedField(
        slug_field="slug", queryset=ProductCategory.objects.all()
    )
    sports = serializers.ListField(
        child=serializers.SlugField(), required=False, help_text="Sport slugs."
    )

    class Meta:
        model = Product
        fields = [
            "category",
            "name",
            "description",
            "image_url",
            "kind",
            "base_price",
            "rental_price_per_match",
            "deposit",
            "perishable",
            "sku",
            "barcode",
            "serving_size",
            "calories",
            "protein_g",
            "carbs_g",
            "fat_g",
            "sugar_g",
            "caffeine_mg",
            "tags",
            "sports",
            "is_active",
        ]

    def validate(self, data):
        kind = data.get("kind", getattr(self.instance, "kind", ProductKind.SALE))
        if kind == ProductKind.RENTAL and not data.get(
            "rental_price_per_match", getattr(self.instance, "rental_price_per_match", None)
        ):
            raise serializers.ValidationError(
                {"rental_price_per_match": "Rental gear needs a price per match."}
            )
        return data


class StockItemSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    available = serializers.IntegerField(read_only=True)
    price = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    is_low = serializers.BooleanField(read_only=True)

    class Meta:
        model = StockItem
        fields = [
            "id",
            "product",
            "on_hand",
            "reserved",
            "available",
            "price",
            "price_override",
            "low_stock_threshold",
            "is_low",
        ]
        read_only_fields = fields


class StockItemWriteSerializer(serializers.Serializer):
    """The two things a turf sets per location, rather than per product."""

    price_override = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True, min_value=0
    )
    low_stock_threshold = serializers.IntegerField(required=False, min_value=0)


class ReceiveStockSerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)


class AdjustStockSerializer(serializers.Serializer):
    delta = serializers.IntegerField()
    reason = serializers.CharField(max_length=200)


class StockMovementSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_type_display", read_only=True)
    actor_name = serializers.SerializerMethodField()
    product_name = serializers.CharField(source="stock_item.product.name", read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            "id",
            "type",
            "type_label",
            "product_name",
            "qty_delta",
            "reserved_delta",
            "reference",
            "actor_name",
            "note",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_blank=True))
    def get_actor_name(self, obj) -> str:
        if not obj.actor:
            return ""
        profile = getattr(obj.actor, "player_profile", None)
        return profile.name if profile else (obj.actor.full_name or obj.actor.email)


class CounterSaleLineSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    line_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = CounterSaleLine
        fields = ["id", "product", "product_name", "quantity", "unit_price", "line_total"]
        read_only_fields = fields


class CounterSaleSerializer(serializers.ModelSerializer):
    lines = CounterSaleLineSerializer(many=True, read_only=True)
    staff_name = serializers.SerializerMethodField()
    change_due = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = CounterSale
        fields = [
            "id",
            "turf",
            "staff_name",
            "customer_phone",
            "booking",
            "lines",
            "total",
            "cash_received",
            "change_due",
            "status",
            "note",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_staff_name(self, obj) -> str:
        return obj.staff.full_name or obj.staff.email


class CounterSaleLineWriteSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)


class CounterSaleWriteSerializer(serializers.Serializer):
    lines = CounterSaleLineWriteSerializer(many=True)
    cash_received = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, min_value=0
    )
    customer_phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    booking_id = serializers.UUIDField(required=False, allow_null=True)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)


class VoidSaleSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=200, required=False, allow_blank=True)


class RentalSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    player_name = serializers.SerializerMethodField()
    status_label = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Rental
        fields = [
            "id",
            "turf",
            "match",
            "booking",
            "product",
            "product_name",
            "player_name",
            "quantity",
            "status",
            "status_label",
            "price",
            "deposit",
            "charges",
            "out_at",
            "returned_at",
            "note",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_player_name(self, obj) -> str:
        profile = getattr(obj.player, "player_profile", None)
        return profile.name if profile else (obj.player.full_name or obj.player.email)


class RentOutSerializer(serializers.Serializer):
    product_id = serializers.UUIDField()
    player_id = serializers.UUIDField(help_text="The player's profile id (D39).")
    quantity = serializers.IntegerField(min_value=1, default=1)
    match_id = serializers.UUIDField(required=False, allow_null=True)
    booking_id = serializers.UUIDField(required=False, allow_null=True)


class SettleRentalSerializer(serializers.Serializer):
    charges = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, min_value=0)


#: Re-exported for the schema's enum naming.
MOVEMENT_TYPES = MovementType.choices
