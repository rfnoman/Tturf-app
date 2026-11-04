from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.utils import player_label
from apps.players.selectors import player_sport_cards, profile_queryset
from apps.players.serializers import PlayerSportCardSerializer
from apps.sports.serializers import SportFormatSerializer, SportSummarySerializer

from .models import (
    JoinRequest,
    Match,
    MatchInvite,
    MatchPlayer,
    Squad,
    SquadInvite,
    SquadMembership,
)


class RosterPlayerSerializer(serializers.Serializer):
    """A roster entry carrying enough profile to render the Phase 01 card."""

    id = serializers.UUIDField()
    player_id = serializers.UUIDField()
    profile_id = serializers.UUIDField(allow_null=True)
    name = serializers.CharField()
    photo_url = serializers.CharField(allow_blank=True)
    area = serializers.CharField(allow_blank=True)
    source = serializers.CharField()
    overall = serializers.IntegerField(allow_null=True)
    is_provisional = serializers.BooleanField()


def roster_entry(entry: MatchPlayer, *, sport_id) -> dict:
    """Flatten a roster row for the UI, with this sport's rating if there is one."""
    profile = getattr(entry.player, "player_profile", None)
    rating = None
    if profile is not None:
        rating = next((r for r in profile.sport_ratings.all() if r.sport_id == sport_id), None)
    return {
        "id": entry.id,
        "player_id": entry.player_id,
        "profile_id": profile.id if profile else None,
        "name": player_label(entry.player),
        "photo_url": profile.photo_url if profile else entry.player.image_url,
        "area": profile.area if profile else "",
        "source": entry.source,
        "overall": rating.overall if rating else None,
        "is_provisional": rating.is_provisional if rating else True,
    }


class SquadSummarySerializer(serializers.ModelSerializer):
    leader_name = serializers.CharField(source="leader.full_name", read_only=True)
    member_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Squad
        fields = [
            "id",
            "name",
            "slug",
            "area",
            "accepts_public_requests",
            "leader_name",
            "member_count",
        ]
        read_only_fields = fields


class SquadMemberSerializer(serializers.ModelSerializer):
    name = serializers.SerializerMethodField()
    player_id = serializers.UUIDField(source="player.id", read_only=True)
    profile_id = serializers.SerializerMethodField()

    class Meta:
        model = SquadMembership
        fields = ["id", "player_id", "profile_id", "name", "role", "status", "joined_at"]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_name(self, obj) -> str:
        return player_label(obj.player)

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_profile_id(self, obj):
        profile = getattr(obj.player, "player_profile", None)
        return profile.id if profile else None


class SquadSerializer(SquadSummarySerializer):
    sports = SportSummarySerializer(many=True, read_only=True)
    members = SquadMemberSerializer(source="memberships", many=True, read_only=True)
    my_role = serializers.SerializerMethodField()

    class Meta(SquadSummarySerializer.Meta):
        fields = [
            *SquadSummarySerializer.Meta.fields,
            "description",
            "sports",
            "members",
            "my_role",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_null=True))
    def get_my_role(self, obj) -> str | None:
        user = getattr(self.context.get("request"), "user", None)
        if not user or not user.is_authenticated:
            return None
        membership = next(
            (
                m
                for m in obj.memberships.all()
                if m.player_id == user.id and m.status == SquadMembership.Status.ACTIVE
            ),
            None,
        )
        return membership.role if membership else None


class SquadWriteSerializer(serializers.ModelSerializer):
    sport_ids = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=SportSummarySerializer.Meta.model.objects.filter(is_active=True),
        source="sports",
        required=False,
    )

    class Meta:
        model = Squad
        fields = ["name", "description", "area", "accepts_public_requests", "sport_ids"]


class SquadInviteSerializer(serializers.ModelSerializer):
    squad = SquadSummarySerializer(read_only=True)
    invited_by_name = serializers.CharField(
        source="invited_by.full_name", read_only=True, default=""
    )

    class Meta:
        model = SquadInvite
        fields = ["id", "squad", "invited_by_name", "message", "status", "created_at"]
        read_only_fields = fields


class JoinRequestSerializer(serializers.ModelSerializer):
    player_name = serializers.SerializerMethodField()
    player_profile_id = serializers.SerializerMethodField()

    class Meta:
        model = JoinRequest
        fields = [
            "id",
            "player_name",
            "player_profile_id",
            "message",
            "status",
            "decision_note",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_player_name(self, obj) -> str:
        return player_label(obj.player)

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_player_profile_id(self, obj):
        profile = getattr(obj.player, "player_profile", None)
        return profile.id if profile else None


class MatchInviteSerializer(serializers.ModelSerializer):
    invited_player_name = serializers.SerializerMethodField()
    invited_by_name = serializers.CharField(
        source="invited_by.full_name", read_only=True, default=""
    )

    class Meta:
        model = MatchInvite
        fields = [
            "id",
            "invited_player_name",
            "invited_by_name",
            "message",
            "status",
            "created_at",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField())
    def get_invited_player_name(self, obj) -> str:
        return player_label(obj.invited_player)


class MatchSummarySerializer(serializers.ModelSerializer):
    """A match board card (DOMAIN §6)."""

    turf_name = serializers.CharField(source="booking.ground.turf.name", read_only=True)
    turf_slug = serializers.CharField(source="booking.ground.turf.slug", read_only=True)
    area = serializers.CharField(source="booking.ground.turf.area", read_only=True)
    ground_name = serializers.CharField(source="booking.ground.name", read_only=True)
    sport = SportSummarySerializer(read_only=True)
    sport_format = SportFormatSerializer(read_only=True)
    starts_at = serializers.DateTimeField(read_only=True)
    ends_at = serializers.DateTimeField(read_only=True)
    price = serializers.DecimalField(
        source="booking.price", max_digits=12, decimal_places=2, read_only=True
    )
    roster_count = serializers.IntegerField(read_only=True)
    needed = serializers.IntegerField(read_only=True)
    squad = SquadSummarySerializer(read_only=True)
    average_rating = serializers.SerializerMethodField()
    distance_km = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = [
            "id",
            "turf_name",
            "turf_slug",
            "area",
            "ground_name",
            "sport",
            "sport_format",
            "starts_at",
            "ends_at",
            "price",
            "capacity",
            "roster_count",
            "needed",
            "visibility",
            "status",
            "squad",
            "average_rating",
            "distance_km",
        ]
        read_only_fields = fields

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_average_rating(self, obj) -> float | None:
        from .selectors import average_rating_for

        return average_rating_for(obj)

    @extend_schema_field(serializers.FloatField(allow_null=True))
    def get_distance_km(self, obj) -> float | None:
        distance = getattr(obj, "distance", None)
        return round(distance.km, 2) if distance is not None else None


class MatchDetailSerializer(MatchSummarySerializer):
    """The match page: roster, and — for the organiser — the decision queues."""

    roster = serializers.SerializerMethodField()
    organiser_name = serializers.SerializerMethodField()
    is_organiser = serializers.SerializerMethodField()
    is_on_roster = serializers.SerializerMethodField()
    can_request = serializers.SerializerMethodField()
    cannot_request_reason = serializers.SerializerMethodField()
    my_invite_id = serializers.SerializerMethodField()
    pending_requests = serializers.SerializerMethodField()
    live_invites = serializers.SerializerMethodField()
    booking_id = serializers.UUIDField(source="booking.id", read_only=True)

    class Meta(MatchSummarySerializer.Meta):
        fields = [
            *MatchSummarySerializer.Meta.fields,
            "notes",
            "booking_id",
            "roster",
            "organiser_name",
            "is_organiser",
            "is_on_roster",
            "can_request",
            "cannot_request_reason",
            "my_invite_id",
            "pending_requests",
            "live_invites",
        ]
        read_only_fields = fields

    def _user(self):
        return getattr(self.context.get("request"), "user", None)

    @extend_schema_field(RosterPlayerSerializer(many=True))
    def get_roster(self, obj) -> list[dict]:
        return [roster_entry(entry, sport_id=obj.sport_id) for entry in obj.players.all()]

    @extend_schema_field(serializers.CharField())
    def get_organiser_name(self, obj) -> str:
        organiser = obj.organiser
        return player_label(organiser)

    @extend_schema_field(serializers.BooleanField())
    def get_is_organiser(self, obj) -> bool:
        from .services import is_organiser

        return is_organiser(match=obj, user=self._user())

    @extend_schema_field(serializers.BooleanField())
    def get_is_on_roster(self, obj) -> bool:
        from .services import is_on_roster

        return is_on_roster(match=obj, user=self._user())

    @extend_schema_field(serializers.BooleanField())
    def get_can_request(self, obj) -> bool:
        from .services import can_request_to_join

        return can_request_to_join(match=obj, user=self._user())[0]

    @extend_schema_field(serializers.CharField(allow_blank=True))
    def get_cannot_request_reason(self, obj) -> str:
        from .services import can_request_to_join

        return can_request_to_join(match=obj, user=self._user())[1]

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_my_invite_id(self, obj):
        """The invitation awaiting *this* reader, so the UI can offer accept/decline."""
        user = self._user()
        if not user or not user.is_authenticated:
            return None
        invite = obj.invites.filter(
            invited_player=user, status=MatchInvite.Status.LEADER_APPROVED
        ).first()
        return invite.id if invite else None

    @extend_schema_field(JoinRequestSerializer(many=True))
    def get_pending_requests(self, obj) -> list[dict]:
        # Only the organiser decides, so only the organiser sees the queue.
        if not self.get_is_organiser(obj):
            return []
        from .selectors import pending_requests_for

        return JoinRequestSerializer(pending_requests_for(obj), many=True).data

    @extend_schema_field(MatchInviteSerializer(many=True))
    def get_live_invites(self, obj) -> list[dict]:
        if not self.get_is_organiser(obj):
            return []
        from .selectors import live_invites_for

        return MatchInviteSerializer(live_invites_for(obj), many=True).data


class JoinRequestCreateSerializer(serializers.Serializer):
    message = serializers.CharField(max_length=300, required=False, allow_blank=True)


class DecideRequestSerializer(serializers.Serializer):
    approve = serializers.BooleanField()
    add_to_squad = serializers.BooleanField(
        required=False, default=False, help_text="Leader only; keeps the player around."
    )
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)


class InvitePlayerSerializer(serializers.Serializer):
    player_id = serializers.UUIDField(help_text="The player's profile id.")
    message = serializers.CharField(max_length=300, required=False, allow_blank=True)


class DecideSerializer(serializers.Serializer):
    approve = serializers.BooleanField()


class RemovePlayerSerializer(serializers.Serializer):
    player_id = serializers.UUIDField(help_text="The player's profile id.")


class MatchPlayerCardSerializer(serializers.Serializer):
    """Phase 01's profile card, for the roster drawer."""

    cards = PlayerSportCardSerializer(many=True)


def profile_card_payload(profile_id):
    """Fetch one roster player's Phase 01 card data."""
    profile = profile_queryset().filter(pk=profile_id).first()
    if profile is None:
        return None
    return player_sport_cards(profile)
