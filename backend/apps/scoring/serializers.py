from __future__ import annotations

from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.core.utils import plain_decimal
from apps.sports.serializers import StatDefinitionSerializer

from .models import (
    MatchResult,
    MatchTeam,
    MotmVote,
    PeerRating,
    Scorecard,
    ScorecardEvent,
    ScorecardStatus,
    TeamSide,
)


def player_label(user) -> str:
    profile = getattr(user, "player_profile", None)
    return profile.name if profile else (user.full_name or user.email)


def profile_id_of(user):
    profile = getattr(user, "player_profile", None)
    return profile.id if profile else None


class TeamPlayerSerializer(serializers.Serializer):
    match_player_id = serializers.UUIDField()
    player_id = serializers.UUIDField()
    profile_id = serializers.UUIDField(allow_null=True)
    name = serializers.CharField()
    position = serializers.CharField(allow_blank=True)
    is_captain = serializers.BooleanField()


class MatchTeamSerializer(serializers.ModelSerializer):
    display_name = serializers.CharField(read_only=True)
    captain_name = serializers.SerializerMethodField()
    players = serializers.SerializerMethodField()
    score = serializers.SerializerMethodField()

    class Meta:
        model = MatchTeam
        fields = ["id", "side", "name", "display_name", "captain_name", "players", "score"]
        read_only_fields = fields

    @extend_schema_field(serializers.CharField(allow_blank=True))
    def get_captain_name(self, obj) -> str:
        return player_label(obj.captain) if obj.captain else ""

    @extend_schema_field(TeamPlayerSerializer(many=True))
    def get_players(self, obj) -> list[dict]:
        return [
            {
                "match_player_id": entry.match_player_id,
                "player_id": entry.match_player.player_id,
                "profile_id": profile_id_of(entry.match_player.player),
                "name": player_label(entry.match_player.player),
                "position": entry.position,
                "is_captain": entry.match_player.player_id == obj.captain_id,
            }
            for entry in obj.players.select_related("match_player__player")
        ]

    @extend_schema_field(serializers.IntegerField(allow_null=True))
    def get_score(self, obj) -> int | None:
        scorecard = getattr(obj.match, "scorecard", None)
        return scorecard.score_for(obj.side) if scorecard else None


class PlayerStatRowSerializer(serializers.Serializer):
    """One player's stats on the scorecard, flattened for display."""

    player_id = serializers.UUIDField()
    profile_id = serializers.UUIDField(allow_null=True)
    name = serializers.CharField()
    side = serializers.CharField(allow_blank=True)
    stats = serializers.DictField(child=serializers.CharField())
    is_motm = serializers.BooleanField()


class ScorecardEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    to_status_label = serializers.CharField(source="get_to_status_display", read_only=True)

    class Meta:
        model = ScorecardEvent
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
        return player_label(obj.actor) if obj.actor else ""


class ScorecardSerializer(serializers.ModelSerializer):
    """The scorecard as everyone sees it, plus what *this* reader may do with it."""

    match_id = serializers.UUIDField(source="match.id", read_only=True)
    sport = serializers.CharField(source="match.sport.name", read_only=True)
    sport_slug = serializers.CharField(source="match.sport.slug", read_only=True)
    turf_name = serializers.CharField(source="match.booking.ground.turf.name", read_only=True)
    ground_name = serializers.CharField(source="match.booking.ground.name", read_only=True)
    played_at = serializers.DateTimeField(source="match.starts_at", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    scorer_name = serializers.SerializerMethodField()
    motm_name = serializers.SerializerMethodField()
    motm_profile_id = serializers.SerializerMethodField()
    teams = MatchTeamSerializer(source="match.teams", many=True, read_only=True)
    stat_definitions = serializers.SerializerMethodField()
    rows = serializers.SerializerMethodField()
    events = ScorecardEventSerializer(many=True, read_only=True)
    # What the reader can do, so the UI does not have to re-derive the rules.
    can_edit = serializers.SerializerMethodField()
    can_confirm = serializers.SerializerMethodField()
    can_resolve = serializers.SerializerMethodField()
    motm_voting_open = serializers.SerializerMethodField()
    my_motm_vote = serializers.SerializerMethodField()
    my_peer_ratings = serializers.SerializerMethodField()

    class Meta:
        model = Scorecard
        fields = [
            "id",
            "match_id",
            "sport",
            "sport_slug",
            "turf_name",
            "ground_name",
            "played_at",
            "team_a_score",
            "team_b_score",
            "extra",
            "result",
            "status",
            "status_label",
            "verified_by_staff",
            "auto_confirmed",
            "dispute_reason",
            "submitted_at",
            "locked_at",
            "scorer_name",
            "motm_name",
            "motm_profile_id",
            "teams",
            "stat_definitions",
            "rows",
            "events",
            "can_edit",
            "can_confirm",
            "can_resolve",
            "motm_voting_open",
            "my_motm_vote",
            "my_peer_ratings",
        ]
        read_only_fields = fields

    def _user(self):
        return getattr(self.context.get("request"), "user", None)

    @extend_schema_field(serializers.CharField(allow_blank=True))
    def get_scorer_name(self, obj) -> str:
        return player_label(obj.scorer) if obj.scorer else ""

    @extend_schema_field(serializers.CharField(allow_blank=True))
    def get_motm_name(self, obj) -> str:
        return player_label(obj.motm) if obj.motm else ""

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_motm_profile_id(self, obj):
        return profile_id_of(obj.motm) if obj.motm else None

    @extend_schema_field(StatDefinitionSerializer(many=True))
    def get_stat_definitions(self, obj) -> list[dict]:
        """The sport's player-scope stats — what the entry form renders from."""
        from apps.sports.models import StatDefinition

        definitions = StatDefinition.objects.filter(
            sport=obj.match.sport_id, scope=StatDefinition.Scope.PLAYER
        )
        return StatDefinitionSerializer(definitions, many=True).data

    @extend_schema_field(PlayerStatRowSerializer(many=True))
    def get_rows(self, obj) -> list[dict]:
        from .models import MatchTeamPlayer

        sides = {
            entry.match_player.player_id: entry.team.side
            for entry in MatchTeamPlayer.objects.filter(team__match=obj.match_id).select_related(
                "team", "match_player"
            )
        }

        by_player: dict = {}
        for row in obj.player_stats.select_related("stat_definition", "player"):
            bucket = by_player.setdefault(
                row.player_id,
                {
                    "player_id": row.player_id,
                    "profile_id": profile_id_of(row.player),
                    "name": player_label(row.player),
                    "side": sides.get(row.player_id, ""),
                    "stats": {},
                    "is_motm": row.player_id == obj.motm_id,
                },
            )
            # Trailing zeros make a scorecard look like a spreadsheet, and a bare
            # `normalize()` turns 100.00 into "1E+2".
            bucket["stats"][row.stat_definition.key] = plain_decimal(row.value)

        return sorted(by_player.values(), key=lambda row: (row["side"], row["name"]))

    @extend_schema_field(serializers.BooleanField())
    def get_can_edit(self, obj) -> bool:
        from .services import can_score

        return obj.is_editable and can_score(match=obj.match, user=self._user())

    @extend_schema_field(serializers.BooleanField())
    def get_can_confirm(self, obj) -> bool:
        from .services import can_confirm

        return obj.status == ScorecardStatus.SUBMITTED and can_confirm(
            scorecard=obj, user=self._user()
        )

    @extend_schema_field(serializers.BooleanField())
    def get_can_resolve(self, obj) -> bool:
        from .services import is_turf_staff

        user = self._user()
        if obj.status != ScorecardStatus.DISPUTED:
            return False
        return bool(
            getattr(user, "is_platform_admin", False)
            or getattr(user, "is_superuser", False)
            or is_turf_staff(match=obj.match, user=user)
        )

    @extend_schema_field(serializers.BooleanField())
    def get_motm_voting_open(self, obj) -> bool:
        from .services import motm_voting_open

        return motm_voting_open(obj)

    @extend_schema_field(serializers.UUIDField(allow_null=True))
    def get_my_motm_vote(self, obj):
        user = self._user()
        if not user or not user.is_authenticated:
            return None
        vote = MotmVote.objects.filter(match=obj.match_id, voter=user).first()
        return profile_id_of(vote.nominee) if vote else None

    @extend_schema_field(serializers.DictField(child=serializers.IntegerField()))
    def get_my_peer_ratings(self, obj) -> dict:
        """What this reader already gave, keyed by profile id.

        Without it the stars come back empty on every reload and a player cannot tell a
        saved rating from an unsaved one.
        """
        user = self._user()
        if not user or not user.is_authenticated:
            return {}
        return {
            str(profile_id_of(rating.ratee)): rating.overall
            for rating in PeerRating.objects.filter(match=obj.match_id, rater=user).select_related(
                "ratee__player_profile"
            )
            if profile_id_of(rating.ratee)
        }


class PublicScorecardSerializer(ScorecardSerializer):
    """The shareable version: no reader-specific permissions or history."""

    class Meta(ScorecardSerializer.Meta):
        fields = [
            field
            for field in ScorecardSerializer.Meta.fields
            if field
            not in {
                "can_edit",
                "can_confirm",
                "can_resolve",
                "motm_voting_open",
                "my_motm_vote",
                "my_peer_ratings",
                "events",
                "dispute_reason",
            }
        ]
        read_only_fields = fields


class SetTeamsSerializer(serializers.Serializer):
    assignments = serializers.DictField(
        child=serializers.ChoiceField(choices=TeamSide.choices),
        help_text='{match_player_id: "A"|"B"}. Anyone omitted is left off a team sheet.',
    )


class SetCaptainSerializer(serializers.Serializer):
    side = serializers.ChoiceField(choices=TeamSide.choices)
    player_id = serializers.UUIDField(allow_null=True, help_text="The player's profile id.")


class AssignScorerSerializer(serializers.Serializer):
    player_id = serializers.UUIDField(help_text="The player's profile id.")


class SaveScorecardSerializer(serializers.Serializer):
    team_a_score = serializers.IntegerField(min_value=0, max_value=999, required=False)
    team_b_score = serializers.IntegerField(min_value=0, max_value=999, required=False)
    stats = serializers.DictField(
        child=serializers.DictField(child=serializers.DecimalField(max_digits=8, decimal_places=2)),
        required=False,
        help_text="{player_id: {stat_key: value}}. Replaces the whole set.",
    )
    extra = serializers.DictField(required=False)


class DisputeSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300)


class ResolveSerializer(SaveScorecardSerializer):
    pass


class MotmVoteSerializer(serializers.Serializer):
    player_id = serializers.UUIDField(help_text="The nominee's profile id.")


class PeerRatingEntrySerializer(serializers.Serializer):
    player_id = serializers.UUIDField()
    overall = serializers.IntegerField(min_value=1, max_value=5)
    skill_taps = serializers.ListField(
        child=serializers.CharField(max_length=40), required=False, default=list
    )


class PeerRatingsSerializer(serializers.Serializer):
    ratings = PeerRatingEntrySerializer(many=True)


class ResultSummarySerializer(serializers.Serializer):
    """A player's recent results, for the profile track record."""

    match_id = serializers.UUIDField()
    scorecard_id = serializers.UUIDField()
    sport = serializers.CharField()
    turf_name = serializers.CharField()
    played_at = serializers.DateTimeField()
    team_a_score = serializers.IntegerField()
    team_b_score = serializers.IntegerField()
    result = serializers.ChoiceField(choices=MatchResult.choices, allow_blank=True)
    my_side = serializers.CharField(allow_blank=True)
    outcome = serializers.CharField(help_text="win, loss or draw, from this player's side.")
    is_motm = serializers.BooleanField()
    verified_by_staff = serializers.BooleanField()
