from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .models import ActivityLog, Bundle, BundleItem, GoalType, ReminderPreference


class ActivityLogSerializer(serializers.ModelSerializer):
    sport_name = serializers.CharField(source="sport.name", read_only=True, allow_null=True)
    turf_name = serializers.SerializerMethodField()

    class Meta:
        model = ActivityLog
        fields = [
            "id",
            "sport_name",
            "turf_name",
            "match",
            "source",
            "happened_on",
            "minutes",
            "est_calories",
            "is_estimate",
            "note",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_blank=True))
    def get_turf_name(self, obj) -> str:
        return obj.match.turf.name if obj.match_id else ""


class ManualActivitySerializer(serializers.Serializer):
    minutes = serializers.IntegerField(min_value=1, max_value=24 * 60)
    happened_on = serializers.DateField(required=False)
    sport = serializers.SlugField(required=False, allow_blank=True, allow_null=True)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)


class SportMinutesSerializer(serializers.Serializer):
    sport = serializers.CharField()
    slug = serializers.SlugField()
    minutes = serializers.IntegerField()
    sessions = serializers.IntegerField()


class WeeklySummarySerializer(serializers.Serializer):
    week_start = serializers.DateField()
    week_end = serializers.DateField()
    minutes = serializers.IntegerField()
    calories = serializers.IntegerField()
    sessions = serializers.IntegerField()
    matches = serializers.IntegerField()
    by_sport = SportMinutesSerializer(many=True)
    is_estimate = serializers.BooleanField()


class StreakSerializer(serializers.Serializer):
    current = serializers.IntegerField()
    best = serializers.IntegerField()
    played_this_week = serializers.BooleanField()


class GoalProgressSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    type = serializers.ChoiceField(choices=GoalType.choices)
    label = serializers.CharField()
    target = serializers.IntegerField()
    achieved = serializers.IntegerField()
    percent = serializers.IntegerField()


class SetGoalSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=GoalType.choices)
    target = serializers.IntegerField(min_value=0, max_value=10_000)


class BundleItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)
    product_id = serializers.UUIDField(read_only=True)

    class Meta:
        model = BundleItem
        fields = ["id", "product_id", "product_name", "quantity"]
        read_only_fields = fields


class BundleSerializer(serializers.ModelSerializer):
    items = BundleItemSerializer(many=True, read_only=True)
    turf_slug = serializers.SerializerMethodField()
    sport_slug = serializers.CharField(source="sport.slug", read_only=True, allow_null=True)
    occasion_label = serializers.CharField(source="get_occasion_display", read_only=True)

    class Meta:
        model = Bundle
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "turf_slug",
            "sport_slug",
            "occasion",
            "occasion_label",
            "image_url",
            "items",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_blank=True))
    def get_turf_slug(self, obj) -> str:
        return obj.turf.slug if obj.turf_id else ""


class BundleResultSerializer(serializers.Serializer):
    added = serializers.ListField(child=serializers.DictField())
    missing = serializers.ListField(child=serializers.CharField())
    source_id = serializers.UUIDField()


class ReminderPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReminderPreference
        fields = [
            "match_day",
            "hydration",
            "recovery",
            "order_cutoff",
            "weekly_recap",
            "push_enabled",
            "quiet_from",
            "quiet_until",
        ]


class PushSubscriptionSerializer(serializers.Serializer):
    endpoint = serializers.URLField(max_length=500)
    p256dh = serializers.CharField(max_length=200)
    auth = serializers.CharField(max_length=100)
    user_agent = serializers.CharField(max_length=200, required=False, allow_blank=True)


class DashboardSerializer(serializers.Serializer):
    """Everything the home screen shows, in one request."""

    week = WeeklySummarySerializer()
    streak = StreakSerializer()
    goals = GoalProgressSerializer(many=True)
    recent = ActivityLogSerializer(many=True)
