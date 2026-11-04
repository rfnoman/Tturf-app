from django.contrib import admin

from .models import (
    Address,
    Cart,
    CartItem,
    DeliveryZone,
    Order,
    OrderEvent,
    OrderItem,
    RiderProfile,
)


@admin.register(DeliveryZone)
class DeliveryZoneAdmin(admin.ModelAdmin):
    list_display = ("name", "fee", "eta_hours", "turf_delivery_cutoff_hours", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("label", "area", "player", "is_default")
    search_fields = ("line", "area", "player__email")
    raw_id_fields = ("player",)


class CartItemInline(admin.TabularInline):
    model = CartItem
    extra = 0
    raw_id_fields = ("stock_item",)


@admin.register(Cart)
class CartAdmin(admin.ModelAdmin):
    list_display = ("player", "updated_at")
    raw_id_fields = ("player",)
    inlines = [CartItemInline]


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    raw_id_fields = ("product", "stock_item")
    # Snapshots: a receipt that changes is not a receipt.
    readonly_fields = ("name", "unit_price", "quantity", "nutrition")


class OrderEventInline(admin.TabularInline):
    model = OrderEvent
    extra = 0
    readonly_fields = ("from_status", "to_status", "actor", "note")

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("created_at", "player", "location", "fulfilment", "total", "status")
    list_filter = ("status", "fulfilment", "location")
    search_fields = ("player__email", "id")
    raw_id_fields = ("player", "location", "match", "address", "zone", "rider")
    # Status moves through the services, which release or commit stock as they go; a
    # hand-edited status would leave the shelf wrong.
    readonly_fields = ("status", "subtotal", "total", "settled_at")
    inlines = [OrderItemInline, OrderEventInline]


@admin.register(RiderProfile)
class RiderProfileAdmin(admin.ModelAdmin):
    list_display = ("user", "phone", "is_active")
    list_filter = ("is_active", "zones")
    raw_id_fields = ("user",)
    filter_horizontal = ("zones",)
