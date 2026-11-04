from django.contrib import admin

from .models import (
    ActivityLog,
    Bundle,
    BundleItem,
    FitnessGoal,
    PushSubscription,
    ReminderPreference,
)


@admin.register(ActivityLog)
class ActivityLogAdmin(admin.ModelAdmin):
    list_display = ("happened_on", "player", "sport", "minutes", "est_calories", "is_estimate")
    list_filter = ("source", "sport", "is_estimate")
    search_fields = ("player__email", "note")
    raw_id_fields = ("player", "sport", "match")


@admin.register(FitnessGoal)
class FitnessGoalAdmin(admin.ModelAdmin):
    list_display = ("player", "type", "target", "is_active")
    list_filter = ("type", "is_active")
    raw_id_fields = ("player",)


class BundleItemInline(admin.TabularInline):
    model = BundleItem
    extra = 1
    raw_id_fields = ("product",)


@admin.register(Bundle)
class BundleAdmin(admin.ModelAdmin):
    list_display = ("name", "turf", "sport", "occasion", "is_active")
    list_filter = ("occasion", "is_active", "sport")
    search_fields = ("name", "slug")
    prepopulated_fields = {"slug": ("name",)}
    raw_id_fields = ("turf", "sport")
    inlines = [BundleItemInline]


@admin.register(ReminderPreference)
class ReminderPreferenceAdmin(admin.ModelAdmin):
    list_display = ("player", "match_day", "hydration", "recovery", "push_enabled")
    list_filter = ("push_enabled", "hydration", "recovery")
    raw_id_fields = ("player",)


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("player", "user_agent", "last_used_at", "created_at")
    search_fields = ("player__email", "endpoint")
    raw_id_fields = ("player",)
    # Written by the browser; a hand-edited key just breaks delivery silently.
    readonly_fields = ("endpoint", "p256dh", "auth")
