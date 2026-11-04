"""Serializers for the platform dashboard and support lookup (Phase 11 step 6)."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from .utils import player_label


class BookingsPerDaySerializer(serializers.Serializer):
    day = serializers.DateField()
    total = serializers.IntegerField()
    confirmed = serializers.IntegerField()


class TopTurfSerializer(serializers.Serializer):
    name = serializers.CharField()
    slug = serializers.SlugField()
    area = serializers.CharField(allow_blank=True)
    bookings = serializers.IntegerField()


class PlatformDashboardSerializer(serializers.Serializer):
    """One screen's worth of "is this working"."""

    period_start = serializers.DateField()
    period_end = serializers.DateField()

    bookings = serializers.IntegerField()
    bookings_confirmed = serializers.IntegerField()
    bookings_cancelled = serializers.IntegerField()
    no_shows = serializers.IntegerField()
    #: Counted against bookings that *reached* their slot, not every booking ever made:
    #: a cancelled booking is not a no-show, and counting it would flatter the number
    #: exactly as the business grew.
    no_show_rate = serializers.FloatField()

    matches = serializers.IntegerField()
    orders = serializers.IntegerField()
    orders_fulfilled = serializers.IntegerField()

    #: A player who did something, not one who exists.
    active_players = serializers.IntegerField()
    new_players = serializers.IntegerField()

    turfs_live = serializers.IntegerField()
    turfs_pending = serializers.IntegerField()

    platform_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)
    commission = serializers.DecimalField(max_digits=12, decimal_places=2)

    per_day = BookingsPerDaySerializer(many=True)
    top_turfs = TopTurfSerializer(many=True)


class PlayerLookupSerializer(serializers.Serializer):
    """What support needs to identify the right person, and nothing more.

    Contact details are included here and nowhere else in the API: support answering
    "I can't see my booking" has to be able to tell two Rafis apart. It is admin-only,
    and there is no impersonation anywhere — an admin can read an account, never act as
    one.
    """

    id = serializers.UUIDField()
    name = serializers.SerializerMethodField()
    email = serializers.EmailField()
    phone = serializers.CharField(allow_blank=True)
    player_profile_id = serializers.SerializerMethodField()
    is_platform_admin = serializers.BooleanField()
    is_active = serializers.BooleanField()
    created_at = serializers.DateTimeField()

    def get_name(self, obj) -> str:
        return player_label(obj)

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_player_profile_id(self, obj):
        profile = getattr(obj, "player_profile", None)
        return profile.id if profile else None
