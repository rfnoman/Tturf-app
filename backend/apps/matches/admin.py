from django.contrib import admin
from django.utils.translation import gettext_lazy as _

from .models import (
    JoinRequest,
    Match,
    MatchInvite,
    MatchPlayer,
    Squad,
    SquadInvite,
    SquadMembership,
)


class SquadMembershipInline(admin.TabularInline):
    model = SquadMembership
    extra = 0
    autocomplete_fields = ("player",)


@admin.register(Squad)
class SquadAdmin(admin.ModelAdmin):
    list_display = ("name", "leader", "area", "accepts_public_requests", "member_count")
    list_filter = ("accepts_public_requests", "area")
    search_fields = ("name", "slug", "leader__email")
    prepopulated_fields = {"slug": ("name",)}
    autocomplete_fields = ("leader", "created_by")
    filter_horizontal = ("sports",)
    inlines = [SquadMembershipInline]

    @admin.display(description=_("members"))
    def member_count(self, obj) -> int:
        return obj.member_count


class MatchPlayerInline(admin.TabularInline):
    model = MatchPlayer
    extra = 0
    autocomplete_fields = ("player",)


class JoinRequestInline(admin.TabularInline):
    model = JoinRequest
    extra = 0
    autocomplete_fields = ("player", "decided_by")
    readonly_fields = ("status", "decided_by", "decided_at")


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = ("__str__", "visibility", "status", "capacity", "roster_count", "squad")
    list_filter = ("status", "visibility", "sport")
    search_fields = ("booking__id", "squad__name")
    autocomplete_fields = ("booking", "squad", "sport", "sport_format")
    # Status and visibility are derived; apps.matches.services owns both.
    readonly_fields = ("visibility", "status", "capacity", "created_at", "updated_at")
    inlines = [MatchPlayerInline, JoinRequestInline]

    @admin.display(description=_("roster"))
    def roster_count(self, obj) -> int:
        return obj.roster_count


@admin.register(JoinRequest)
class JoinRequestAdmin(admin.ModelAdmin):
    list_display = ("match", "player", "status", "decided_by", "decided_at")
    list_filter = ("status",)
    search_fields = ("player__email",)
    autocomplete_fields = ("match", "player", "decided_by")


@admin.register(MatchInvite)
class MatchInviteAdmin(admin.ModelAdmin):
    list_display = ("match", "invited_player", "invited_by", "status", "decided_at")
    list_filter = ("status",)
    search_fields = ("invited_player__email",)
    autocomplete_fields = ("match", "invited_player", "invited_by", "approved_by")


@admin.register(SquadInvite)
class SquadInviteAdmin(admin.ModelAdmin):
    list_display = ("squad", "player", "invited_by", "status", "decided_at")
    list_filter = ("status",)
    search_fields = ("player__email", "squad__name")
    autocomplete_fields = ("squad", "player", "invited_by")


@admin.register(SquadMembership)
class SquadMembershipAdmin(admin.ModelAdmin):
    list_display = ("squad", "player", "role", "status", "joined_at")
    list_filter = ("role", "status")
    search_fields = ("player__email", "squad__name")
    autocomplete_fields = ("squad", "player")
