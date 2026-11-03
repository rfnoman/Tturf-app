from django.contrib import admin

from .models import Booking, BookingEvent


class BookingEventInline(admin.TabularInline):
    model = BookingEvent
    extra = 0
    # Append-only history: editing it would defeat the point of keeping it.
    readonly_fields = ("from_status", "to_status", "actor", "note", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ("ground", "player_name", "starts_at", "status", "price", "created_at")
    list_filter = ("status", "mode", "visibility", "ground__turf")
    search_fields = ("booked_by__email", "booked_for_name", "booked_for_phone", "id")
    autocomplete_fields = ("ground", "booked_by", "sport", "sport_format")
    # Status moves only through apps.bookings.services, never by hand.
    readonly_fields = (
        "status",
        "time_range",
        "confirmed_by",
        "confirmed_at",
        "cancelled_by",
        "cancelled_at",
        "was_late_cancel",
        "auto_confirmed",
        "created_at",
        "updated_at",
    )
    inlines = [BookingEventInline]

    @admin.display(description="starts")
    def starts_at(self, obj):
        return obj.starts_at


@admin.register(BookingEvent)
class BookingEventAdmin(admin.ModelAdmin):
    list_display = ("booking", "from_status", "to_status", "actor", "created_at")
    list_filter = ("to_status",)
    search_fields = ("booking__id",)
