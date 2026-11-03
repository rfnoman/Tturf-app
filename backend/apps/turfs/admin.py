"""Turf administration — the review queue and support access."""

from __future__ import annotations

from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from .models import (
    Amenity,
    Closure,
    Ground,
    OperatingHours,
    PriceRule,
    Turf,
    TurfMembership,
    TurfPhoto,
)
from .services import approve_turf, suspend_turf


@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ("label", "key", "icon", "order")
    search_fields = ("label", "key")
    ordering = ("order",)


class GroundInline(admin.TabularInline):
    model = Ground
    extra = 0
    show_change_link = True
    fields = ("name", "surface", "max_players", "slot_minutes", "is_active")
    readonly_fields = ("is_active",)


class OperatingHoursInline(admin.TabularInline):
    model = OperatingHours
    extra = 0


class TurfPhotoInline(admin.TabularInline):
    model = TurfPhoto
    extra = 0


class TurfMembershipInline(admin.TabularInline):
    model = TurfMembership
    extra = 0
    fk_name = "turf"
    autocomplete_fields = ("user", "invited_by")
    fields = ("user", "invited_email", "role", "status", "accepted_at")
    readonly_fields = ("accepted_at",)


@admin.register(Turf)
class TurfAdmin(admin.ModelAdmin):
    list_display = ("name", "area", "city", "status", "ground_count", "submitted_at")
    list_filter = ("status", "city", "area")
    search_fields = ("name", "area", "address", "slug")
    prepopulated_fields = {"slug": ("name",)}
    filter_horizontal = ("amenities",)
    readonly_fields = ("reviewed_by", "reviewed_at", "submitted_at", "created_at", "updated_at")
    inlines = [GroundInline, OperatingHoursInline, TurfPhotoInline, TurfMembershipInline]
    actions = ("approve_selected", "suspend_selected")

    @admin.display(description=_("grounds"))
    def ground_count(self, obj) -> int:
        return obj.grounds.count()

    def _run(self, request, queryset, service, **kwargs):
        done = 0
        for turf in queryset:
            try:
                service(turf=turf, reviewer=request.user, **kwargs)
            except ValidationError as exc:
                self.message_user(
                    request, f"{turf.name}: {'; '.join(exc.messages)}", messages.ERROR
                )
                continue
            done += 1
        if done:
            self.message_user(request, f"Updated {done} turf(s).", messages.SUCCESS)

    @admin.action(description=_("Approve selected turfs"))
    def approve_selected(self, request, queryset):
        self._run(request, queryset, approve_turf)

    @admin.action(description=_("Suspend selected turfs"))
    def suspend_selected(self, request, queryset):
        self._run(request, queryset, suspend_turf, reason="Suspended from the admin.")


class PriceRuleInline(admin.TabularInline):
    model = PriceRule
    extra = 0


@admin.register(Ground)
class GroundAdmin(admin.ModelAdmin):
    list_display = ("name", "turf", "surface", "max_players", "slot_minutes", "is_active")
    list_filter = ("is_active", "surface", "turf__area")
    search_fields = ("name", "turf__name")
    autocomplete_fields = ("turf",)
    filter_horizontal = ("sport_formats",)
    prepopulated_fields = {"slug": ("name",)}
    inlines = [PriceRuleInline]


@admin.register(TurfMembership)
class TurfMembershipAdmin(admin.ModelAdmin):
    list_display = ("turf", "user", "invited_email", "role", "status", "accepted_at")
    list_filter = ("role", "status")
    search_fields = ("turf__name", "user__email", "invited_email")
    autocomplete_fields = ("turf", "user", "invited_by")


@admin.register(Closure)
class ClosureAdmin(admin.ModelAdmin):
    list_display = ("turf", "ground", "starts_at", "ends_at", "reason")
    list_filter = ("turf",)
    autocomplete_fields = ("turf", "ground")


@admin.register(PriceRule)
class PriceRuleAdmin(admin.ModelAdmin):
    list_display = ("ground", "label", "start_time", "end_time", "price")
    list_filter = ("ground__turf", "label")
    autocomplete_fields = ("ground",)
