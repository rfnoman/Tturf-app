from django.contrib import admin

from .models import (
    CounterSale,
    CounterSaleLine,
    Product,
    ProductCategory,
    Rental,
    StockItem,
    StockLocation,
    StockMovement,
)


@admin.register(ProductCategory)
class ProductCategoryAdmin(admin.ModelAdmin):
    list_display = ("label", "slug", "order", "is_consumable")
    search_fields = ("label", "slug")


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("name", "owner_type", "turf", "category", "kind", "base_price", "is_active")
    list_filter = ("owner_type", "kind", "category", "is_active")
    search_fields = ("name", "slug", "sku", "barcode")
    raw_id_fields = ("turf",)
    filter_horizontal = ("sports",)


@admin.register(StockLocation)
class StockLocationAdmin(admin.ModelAdmin):
    list_display = ("name", "kind", "turf", "is_active")
    list_filter = ("kind", "is_active")
    raw_id_fields = ("turf",)


class StockMovementInline(admin.TabularInline):
    model = StockMovement
    extra = 0
    can_delete = False
    readonly_fields = ("type", "qty_delta", "reserved_delta", "reference", "actor", "note")

    def has_add_permission(self, request, obj=None) -> bool:
        return False


@admin.register(StockItem)
class StockItemAdmin(admin.ModelAdmin):
    list_display = ("product", "location", "on_hand", "reserved", "available", "is_low")
    list_filter = ("location",)
    search_fields = ("product__name",)
    raw_id_fields = ("location", "product")
    # Quantities move through services so the ledger stays true; the admin may set the
    # two fields that are nobody's ledger.
    readonly_fields = ("on_hand", "reserved")
    inlines = [StockMovementInline]

    @admin.display(description="available")
    def available(self, obj) -> int:
        return obj.available


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ("created_at", "stock_item", "type", "qty_delta", "reserved_delta", "actor")
    list_filter = ("type",)
    search_fields = ("reference", "note", "stock_item__product__name")
    raw_id_fields = ("stock_item", "actor")
    readonly_fields = tuple(field.name for field in StockMovement._meta.fields)

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        # Append-only: a correction is another movement, never an edit.
        return False


class CounterSaleLineInline(admin.TabularInline):
    model = CounterSaleLine
    extra = 0
    raw_id_fields = ("product",)


@admin.register(CounterSale)
class CounterSaleAdmin(admin.ModelAdmin):
    list_display = ("created_at", "turf", "total", "status", "staff")
    list_filter = ("status", "turf")
    raw_id_fields = ("turf", "staff", "customer", "booking")
    inlines = [CounterSaleLineInline]


@admin.register(Rental)
class RentalAdmin(admin.ModelAdmin):
    list_display = ("product", "turf", "player", "quantity", "status", "out_at", "returned_at")
    list_filter = ("status", "turf")
    raw_id_fields = ("turf", "match", "booking", "player", "product")
