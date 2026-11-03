from django.contrib import admin

from .models import (
    Availability,
    ConductReport,
    LeaderboardEntry,
    PlayerGroundStats,
    PlayerSportStats,
    RatingChange,
)


@admin.register(RatingChange)
class RatingChangeAdmin(admin.ModelAdmin):
    list_display = ("profile", "sport", "before_overall", "after_overall", "played_at")
    list_filter = ("sport", "weights_version")
    search_fields = ("profile__display_name", "profile__user__email")
    raw_id_fields = ("profile", "match")
    # Everything here is the engine's output; editing it by hand would make the stored
    # explanation a lie.
    readonly_fields = tuple(field.name for field in RatingChange._meta.fields)

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(PlayerSportStats)
class PlayerSportStatsAdmin(admin.ModelAdmin):
    list_display = ("profile", "sport", "matches", "wins", "motm_awards")
    list_filter = ("sport",)
    search_fields = ("profile__display_name",)
    raw_id_fields = ("profile",)


@admin.register(PlayerGroundStats)
class PlayerGroundStatsAdmin(admin.ModelAdmin):
    list_display = ("profile", "turf", "ground", "sport", "matches", "motm_awards")
    list_filter = ("sport", "turf")
    search_fields = ("profile__display_name", "turf__name")
    raw_id_fields = ("profile", "turf", "ground")


@admin.register(ConductReport)
class ConductReportAdmin(admin.ModelAdmin):
    list_display = ("reported", "reason", "status", "reporter", "created_at")
    list_filter = ("status", "reason")
    search_fields = ("reported__email", "reporter__email", "details")
    raw_id_fields = ("match", "reporter", "reported", "reviewed_by")


@admin.register(Availability)
class AvailabilityAdmin(admin.ModelAdmin):
    list_display = ("profile", "sport", "starts_at", "ends_at", "area")
    list_filter = ("sport",)
    search_fields = ("profile__display_name", "area")
    raw_id_fields = ("profile",)


@admin.register(LeaderboardEntry)
class LeaderboardEntryAdmin(admin.ModelAdmin):
    list_display = ("rank", "profile", "metric", "sport", "turf", "period", "value")
    list_filter = ("metric", "period", "sport", "turf")
    search_fields = ("profile__display_name",)
    raw_id_fields = ("profile", "turf")

    def has_add_permission(self, request) -> bool:
        # Written nightly by `ratings.rebuild_leaderboards`; a hand-added row would be
        # deleted by the next run.
        return False
