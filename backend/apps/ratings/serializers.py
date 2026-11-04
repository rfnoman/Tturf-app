from __future__ import annotations

from drf_spectacular.utils import extend_schema_field, extend_schema_serializer
from rest_framework import serializers

from apps.core.utils import player_label
from apps.players.serializers import (
    PlayerSportCardSerializer,
    PublicPlayerProfileSerializer,
)

from .models import Availability, ConductReport, LeaderboardEntry, RatingChange


class RatingChangeSerializer(serializers.ModelSerializer):
    """One match's effect, with the engine's own explanation attached."""

    turf_name = serializers.CharField(source="match.booking.ground.turf.name", read_only=True)
    sport = serializers.CharField(source="sport.display_name", read_only=True)
    delta = serializers.IntegerField(read_only=True)

    class Meta:
        model = RatingChange
        fields = [
            "id",
            "match",
            "sport",
            "turf_name",
            "before_overall",
            "after_overall",
            "delta",
            "breakdown",
            "weights_version",
            "played_at",
        ]
        read_only_fields = fields


class TrackRecordEntrySerializer(serializers.Serializer):
    """A player's record at one ground."""

    turf_name = serializers.CharField()
    turf_slug = serializers.SlugField()
    ground_name = serializers.CharField()
    sport = serializers.CharField()
    matches = serializers.IntegerField()
    wins = serializers.IntegerField()
    draws = serializers.IntegerField()
    losses = serializers.IntegerField()
    motm_awards = serializers.IntegerField()
    stat_totals = serializers.DictField(child=serializers.CharField())


class SportTotalsSerializer(serializers.Serializer):
    """Career totals in one sport, plus the last few results."""

    sport = serializers.CharField()
    matches = serializers.IntegerField()
    wins = serializers.IntegerField()
    draws = serializers.IntegerField()
    losses = serializers.IntegerField()
    motm_awards = serializers.IntegerField()
    stat_totals = serializers.DictField(child=serializers.CharField())
    form = serializers.ListField(child=serializers.CharField())


class TrackRecordSerializer(serializers.Serializer):
    """Everything the track-record tab shows."""

    grounds = TrackRecordEntrySerializer(many=True)
    totals = serializers.DictField(child=SportTotalsSerializer())


class FairPlaySerializer(serializers.Serializer):
    score = serializers.IntegerField()
    band = serializers.CharField()
    yellow_cards = serializers.IntegerField()
    red_cards = serializers.IntegerField()
    upheld_reports = serializers.IntegerField()


@extend_schema_serializer(component_name="PlayerAvailability")
class AvailabilitySerializer(serializers.ModelSerializer):
    """Named `PlayerAvailability` in the schema: `apps.turfs` already has an
    `Availability` component meaning a ground's open slots, and two components with one
    name silently produce a wrong client."""

    sport_slug = serializers.SlugField(source="sport.slug", read_only=True, allow_null=True)
    sport_name = serializers.CharField(source="sport.display_name", read_only=True, allow_null=True)

    class Meta:
        model = Availability
        fields = ["id", "sport_slug", "sport_name", "starts_at", "ends_at", "area", "note"]
        read_only_fields = ["id", "sport_slug", "sport_name"]


@extend_schema_serializer(component_name="PlayerAvailabilityWrite")
class AvailabilityWriteSerializer(serializers.Serializer):
    sport = serializers.SlugField(required=False, allow_null=True, allow_blank=True)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    area = serializers.CharField(max_length=120, required=False, allow_blank=True)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate(self, data):
        if data["ends_at"] <= data["starts_at"]:
            raise serializers.ValidationError({"ends_at": "The window has to end after it starts."})
        return data


class PlayerSearchResultSerializer(PublicPlayerProfileSerializer):
    """A search hit: the public profile card, plus when they said they are free."""

    availability = serializers.SerializerMethodField()
    # The profile *view* attaches this to a single instance; a list has to build it per
    # row. `profile_queryset()` has already prefetched everything it reads, so this is
    # Python over prefetched lists rather than a query per player.
    sport_cards = serializers.SerializerMethodField()

    class Meta(PublicPlayerProfileSerializer.Meta):
        fields = [*PublicPlayerProfileSerializer.Meta.fields, "availability"]
        read_only_fields = fields

    @extend_schema_field(PlayerSportCardSerializer(many=True))
    def get_sport_cards(self, obj) -> list[dict]:
        from apps.players.selectors import player_sport_cards

        return PlayerSportCardSerializer(player_sport_cards(obj), many=True).data

    @extend_schema_field(AvailabilitySerializer(many=True))
    def get_availability(self, obj) -> list[dict]:
        from .selectors import availability_for

        return AvailabilitySerializer(availability_for(profile=obj)[:3], many=True).data


class ConductReportSerializer(serializers.ModelSerializer):
    reporter_name = serializers.SerializerMethodField()
    reported_name = serializers.SerializerMethodField()
    reason_label = serializers.CharField(source="get_reason_display", read_only=True)
    match_summary = serializers.SerializerMethodField()

    class Meta:
        model = ConductReport
        fields = [
            "id",
            "match",
            "match_summary",
            "reporter_name",
            "reported_name",
            "reason",
            "reason_label",
            "details",
            "status",
            "review_note",
            "reviewed_at",
            "created_at",
        ]
        read_only_fields = fields

    def _name(self, user) -> str:
        return player_label(user)

    @extend_schema_field(serializers.CharField())
    def get_reporter_name(self, obj) -> str:
        return self._name(obj.reporter)

    @extend_schema_field(serializers.CharField())
    def get_reported_name(self, obj) -> str:
        return self._name(obj.reported)

    @extend_schema_field(serializers.CharField())
    def get_match_summary(self, obj) -> str:
        match = obj.match
        return f"{match.sport.display_name} at {match.turf.name}"


class ConductReportCreateSerializer(serializers.Serializer):
    player_id = serializers.UUIDField(help_text="The reported player's profile id.")
    reason = serializers.ChoiceField(choices=ConductReport.Reason.choices)
    details = serializers.CharField(max_length=1000, required=False, allow_blank=True)


class ConductReviewSerializer(serializers.Serializer):
    uphold = serializers.BooleanField()
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)


class LeaderboardEntrySerializer(serializers.ModelSerializer):
    player_name = serializers.SerializerMethodField()
    player_id = serializers.UUIDField(source="profile_id", read_only=True)
    photo_url = serializers.CharField(source="profile.photo_url", read_only=True)

    class Meta:
        model = LeaderboardEntry
        fields = [
            "id",
            "rank",
            "player_id",
            "player_name",
            "photo_url",
            "value",
            "metric",
            "stat_key",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_player_name(self, obj) -> str:
        return obj.profile.name
