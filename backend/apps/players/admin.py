"""Player profile administration — support-oriented, read-mostly."""

from __future__ import annotations

from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (
    PlayerAttribute,
    PlayerProfile,
    PlayerSkill,
    PlayerSport,
    PlayerSportRating,
)


class PlayerSportInline(admin.TabularInline):
    model = PlayerSport
    extra = 0
    autocomplete_fields = ("sport",)
    fields = ("sport", "positions", "is_verified", "is_hidden")


class PlayerAttributeInline(admin.TabularInline):
    model = PlayerAttribute
    extra = 0
    autocomplete_fields = ("attribute",)
    fields = ("attribute", "value", "source")


class PlayerSportRatingInline(admin.TabularInline):
    model = PlayerSportRating
    extra = 0
    autocomplete_fields = ("sport",)
    # Overalls are written only by apps.players.services.refresh_sport_rating (and from
    # Phase 06 by the rating engine), so they are not editable by hand here.
    readonly_fields = ("overall", "is_provisional", "matches_counted")
    fields = (
        "sport",
        "overall",
        "is_provisional",
        "matches_counted",
        "matches_played",
        "wins",
        "draws",
        "losses",
        "motm_awards",
    )


@admin.register(PlayerProfile)
class PlayerProfileAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "area",
        "reliability_score",
        "onboarding_completed",
        "discoverable",
        "sport_count",
        "created_at",
    )
    list_filter = ("onboarding_completed", "discoverable", "gender", "area")
    search_fields = ("display_name", "user__email", "user__first_name", "user__last_name")
    autocomplete_fields = ("user",)
    readonly_fields = ("created_at", "updated_at", "onboarding_completed_at")
    inlines = [PlayerSportInline, PlayerAttributeInline, PlayerSportRatingInline]

    @admin.display(description=_("sports"))
    def sport_count(self, obj) -> int:
        return obj.player_sports.filter(is_hidden=False).count()


@admin.register(PlayerSkill)
class PlayerSkillAdmin(admin.ModelAdmin):
    list_display = ("profile", "sport_skill", "value", "source")
    list_filter = ("source", "sport_skill__sport")
    search_fields = ("profile__display_name", "sport_skill__label")
    autocomplete_fields = ("profile", "sport_skill")


@admin.register(PlayerSportRating)
class PlayerSportRatingAdmin(admin.ModelAdmin):
    list_display = (
        "profile",
        "sport",
        "overall",
        "is_provisional",
        "matches_played",
        "wins",
        "motm_awards",
    )
    list_filter = ("sport", "is_provisional")
    search_fields = ("profile__display_name",)
    autocomplete_fields = ("profile", "sport")
    readonly_fields = ("overall", "is_provisional")
