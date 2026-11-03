from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.sports.serializers import SportFormatSerializer, SportSummarySerializer

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


class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = ["id", "key", "label", "icon", "order"]


class TurfPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TurfPhoto
        fields = ["id", "image", "caption", "order"]


class PriceRuleSerializer(serializers.ModelSerializer):
    weekdays = serializers.ListField(
        child=serializers.IntegerField(min_value=0, max_value=6),
        # `required=False` would make it optional in the *response* too, even though the
        # model default guarantees a list; COMPONENT_SPLIT_REQUEST keeps the request
        # side lenient through `default`.
        default=list,
        help_text="Monday is 0. Empty means every day.",
    )

    class Meta:
        model = PriceRule
        fields = ["id", "weekdays", "start_time", "end_time", "price", "label"]
        extra_kwargs = {
            "end_time": {
                "help_text": (
                    "An end at or before the start wraps past midnight — 22:00–02:00 is "
                    "a night rate. Equal times therefore mean the full 24 hours, which "
                    "is how a turf prices every open minute with one rule."
                )
            }
        }


class OperatingHoursSerializer(serializers.ModelSerializer):
    weekday_label = serializers.CharField(source="get_weekday_display", read_only=True)
    crosses_midnight = serializers.BooleanField(read_only=True)

    class Meta:
        model = OperatingHours
        fields = ["id", "weekday", "weekday_label", "open_time", "close_time", "crosses_midnight"]


class ClosureSerializer(serializers.ModelSerializer):
    class Meta:
        model = Closure
        fields = ["id", "ground", "starts_at", "ends_at", "reason"]

    def validate(self, attrs):
        starts, ends = attrs.get("starts_at"), attrs.get("ends_at")
        if starts and ends and ends <= starts:
            raise serializers.ValidationError({"ends_at": "A closure must end after it starts."})
        return attrs


class GroundSerializer(serializers.ModelSerializer):
    sport_formats = SportFormatSerializer(many=True, read_only=True)
    sports = SportSummarySerializer(many=True, read_only=True)
    price_rules = PriceRuleSerializer(many=True, read_only=True)
    surface_label = serializers.CharField(source="get_surface_display", read_only=True)

    class Meta:
        model = Ground
        fields = [
            "id",
            "name",
            "slug",
            "surface",
            "surface_label",
            "max_players",
            "slot_minutes",
            "is_active",
            "notes",
            "sport_formats",
            "sports",
            "price_rules",
        ]
        # Response-only: writes go through GroundWriteSerializer. Declaring every field
        # read-only is what makes them *required* in the generated response type —
        # otherwise a model default (slot_minutes, max_players) reads as `number |
        # undefined` on the client even though it is always present.
        read_only_fields = fields


class GroundWriteSerializer(serializers.ModelSerializer):
    sport_format_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=SportFormatSerializer.Meta.model.objects.filter(is_active=True),
        source="sport_formats",
        required=False,
    )

    class Meta:
        model = Ground
        fields = [
            "name",
            "surface",
            "max_players",
            "slot_minutes",
            "notes",
            "sport_format_ids",
        ]


class TurfSummarySerializer(serializers.ModelSerializer):
    """What a listing row needs: identity, position, and what can be played."""

    latitude = serializers.FloatField(read_only=True)
    longitude = serializers.FloatField(read_only=True)
    amenities = AmenitySerializer(many=True, read_only=True)
    photos = TurfPhotoSerializer(many=True, read_only=True)
    sports = serializers.SerializerMethodField()
    ground_count = serializers.SerializerMethodField()
    price_from = serializers.SerializerMethodField()
    distance_km = serializers.SerializerMethodField()

    class Meta:
        model = Turf
        fields = [
            "id",
            "name",
            "slug",
            "area",
            "city",
            "address",
            "latitude",
            "longitude",
            "amenities",
            "photos",
            "sports",
            "ground_count",
            "price_from",
            "distance_km",
        ]

    @extend_schema_field(SportSummarySerializer(many=True))
    def get_sports(self, obj) -> list[dict]:
        seen: dict[str, object] = {}
        for ground in obj.grounds.all():
            for fmt in ground.sport_formats.all():
                seen.setdefault(fmt.sport.slug, fmt.sport)
        ordered = sorted(seen.values(), key=lambda s: (s.order, s.name))
        return SportSummarySerializer(ordered, many=True).data

    @extend_schema_field(serializers.IntegerField())
    def get_ground_count(self, obj) -> int:
        return len(obj.grounds.all())

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_price_from(self, obj) -> str | None:
        """Cheapest slot price across the turf's active grounds, for the listing card."""
        prices = [rule.price for ground in obj.grounds.all() for rule in ground.price_rules.all()]
        return str(min(prices)) if prices else None

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_distance_km(self, obj) -> float | None:
        """Only present when the request supplied a point to measure from."""
        distance = getattr(obj, "distance", None)
        return round(distance.km, 2) if distance is not None else None


class TurfDetailSerializer(TurfSummarySerializer):
    grounds = GroundSerializer(many=True, read_only=True)
    operating_hours = OperatingHoursSerializer(many=True, read_only=True)

    class Meta(TurfSummarySerializer.Meta):
        fields = [
            *TurfSummarySerializer.Meta.fields,
            "description",
            "phone",
            "cancellation_free_hours",
            "grounds",
            "operating_hours",
        ]


class OwnerTurfSerializer(TurfDetailSerializer):
    """The owner's own view: status and review feedback, which players never see."""

    status_label = serializers.CharField(source="get_status_display", read_only=True)
    my_role = serializers.SerializerMethodField()

    class Meta(TurfDetailSerializer.Meta):
        fields = [
            *TurfDetailSerializer.Meta.fields,
            "status",
            "status_label",
            "rejection_reason",
            "submitted_at",
            "reviewed_at",
            "auto_confirm_enabled",
            "my_role",
        ]

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_my_role(self, obj) -> str | None:
        user = getattr(self.context.get("request"), "user", None)
        if not user or not user.is_authenticated:
            return None
        membership = next(
            (
                m
                for m in obj.memberships.all()
                if m.user_id == user.id and m.status == TurfMembership.Status.ACTIVE
            ),
            None,
        )
        return membership.role if membership else None


class TurfWriteSerializer(serializers.ModelSerializer):
    latitude = serializers.FloatField(write_only=True, min_value=-90, max_value=90)
    longitude = serializers.FloatField(write_only=True, min_value=-180, max_value=180)
    amenity_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Amenity.objects.all(), source="amenities", required=False
    )

    class Meta:
        model = Turf
        fields = [
            "name",
            "description",
            "address",
            "area",
            "city",
            "phone",
            "latitude",
            "longitude",
            "amenity_ids",
            "auto_confirm_enabled",
            "cancellation_free_hours",
        ]


class TurfMembershipSerializer(serializers.ModelSerializer):
    user_name = serializers.CharField(source="user.full_name", read_only=True, default="")
    user_email = serializers.CharField(source="user.email", read_only=True, default="")
    role_label = serializers.CharField(source="get_role_display", read_only=True)
    turf_name = serializers.CharField(source="turf.name", read_only=True)

    class Meta:
        model = TurfMembership
        fields = [
            "id",
            "turf",
            "turf_name",
            "user_name",
            "user_email",
            "invited_email",
            "invited_phone",
            "role",
            "role_label",
            "status",
            "accepted_at",
            "created_at",
        ]
        read_only_fields = fields


class StaffInviteSerializer(serializers.Serializer):
    role = serializers.ChoiceField(
        choices=[
            (TurfMembership.Role.MANAGER, TurfMembership.Role.MANAGER.label),
            (TurfMembership.Role.CASHIER, TurfMembership.Role.CASHIER.label),
        ]
    )
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False, allow_blank=True)


class ReviewDecisionSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class SlotSerializer(serializers.Serializer):
    """One slot from ``apps.turfs.availability``."""

    start = serializers.DateTimeField()
    end = serializers.DateTimeField()
    price = serializers.DecimalField(max_digits=12, decimal_places=2, allow_null=True)
    label = serializers.CharField(allow_blank=True)
    available = serializers.BooleanField()
    reason = serializers.CharField(allow_blank=True)
    minutes = serializers.IntegerField(read_only=True)


class AvailabilitySerializer(serializers.Serializer):
    ground_id = serializers.UUIDField()
    date = serializers.DateField()
    slot_minutes = serializers.IntegerField()
    slots = SlotSerializer(many=True)


class PriceCoverageGapSerializer(serializers.Serializer):
    weekday = serializers.ChoiceField(choices=Weekday.choices)
    weekday_label = serializers.CharField()
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
