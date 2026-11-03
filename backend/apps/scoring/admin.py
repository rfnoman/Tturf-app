from django.contrib import admin

from .models import (
    MatchTeam,
    MatchTeamPlayer,
    MotmVote,
    PeerRating,
    PlayerStat,
    Scorecard,
    ScorecardEvent,
)


class MatchTeamPlayerInline(admin.TabularInline):
    model = MatchTeamPlayer
    extra = 0
    # `MatchPlayer` is edited inline on `Match` and has no admin of its own, so it
    # cannot be an autocomplete target; a raw id keeps the page usable regardless.
    raw_id_fields = ("match_player",)


@admin.register(MatchTeam)
class MatchTeamAdmin(admin.ModelAdmin):
    list_display = ("match", "side", "name", "captain")
    list_filter = ("side",)
    search_fields = ("match__id", "name")
    autocomplete_fields = ("match", "captain")
    inlines = [MatchTeamPlayerInline]


class PlayerStatInline(admin.TabularInline):
    model = PlayerStat
    extra = 0
    autocomplete_fields = ("player", "stat_definition")


class ScorecardEventInline(admin.TabularInline):
    model = ScorecardEvent
    extra = 0
    # Append-only history.
    readonly_fields = ("from_status", "to_status", "actor", "note", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Scorecard)
class ScorecardAdmin(admin.ModelAdmin):
    list_display = (
        "match",
        "team_a_score",
        "team_b_score",
        "status",
        "verified_by_staff",
        "motm",
    )
    list_filter = ("status", "verified_by_staff", "auto_confirmed")
    search_fields = ("match__id",)
    autocomplete_fields = ("match", "scorer", "confirmed_by", "resolved_by", "motm")
    # Status moves only through apps.scoring.services.
    readonly_fields = (
        "status",
        "result",
        "submitted_at",
        "confirmed_at",
        "locked_at",
        "motm_closed_at",
        "created_at",
        "updated_at",
    )
    inlines = [PlayerStatInline, ScorecardEventInline]


@admin.register(MotmVote)
class MotmVoteAdmin(admin.ModelAdmin):
    list_display = ("match", "voter", "nominee", "created_at")
    search_fields = ("match__id",)
    autocomplete_fields = ("match", "voter", "nominee")


@admin.register(PeerRating)
class PeerRatingAdmin(admin.ModelAdmin):
    # Deliberately does not list the rater: peer ratings are anonymous to recipients,
    # and support should not casually see who said what either.
    list_display = ("match", "ratee", "overall", "created_at")
    list_filter = ("overall",)
    search_fields = ("match__id",)
    autocomplete_fields = ("match", "rater", "ratee")
