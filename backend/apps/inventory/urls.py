"""Inventory routes.

Spelled out rather than routed through a nested-router package, matching `apps.turfs`:
the owner area has one shape and a flat list is easier to read than a registry.
"""

from django.urls import path

from .views import (
    MyCounterSaleView,
    MyCounterSaleVoidView,
    MyMovementLogView,
    MyProductDetailView,
    MyProductListView,
    MyRentalListView,
    MyRentalLostView,
    MyRentalSettleView,
    MyStockAdjustView,
    MyStockItemView,
    MyStockListView,
    MyStockMovementsView,
    MyStockReceiveView,
    PlatformProductListView,
    ProductCategoryListView,
    TurfProductListView,
    WarehouseProductListView,
    WarehouseStockItemView,
    WarehouseStockView,
)

urlpatterns = [
    # Public reads
    path("product-categories", ProductCategoryListView.as_view(), name="product-categories"),
    path("turfs/<slug:slug>/products", TurfProductListView.as_view(), name="turf-products"),
    path("store/products", PlatformProductListView.as_view(), name="platform-products"),
    # A turf's own shelf
    path("me/turfs/<slug:slug>/products", MyProductListView.as_view(), name="my-products"),
    path(
        "me/turfs/<slug:slug>/products/<uuid:product_id>",
        MyProductDetailView.as_view(),
        name="my-product-detail",
    ),
    path("me/turfs/<slug:slug>/stock", MyStockListView.as_view(), name="my-stock"),
    path(
        "me/turfs/<slug:slug>/stock/<uuid:item_id>",
        MyStockItemView.as_view(),
        name="my-stock-item",
    ),
    path(
        "me/turfs/<slug:slug>/stock/<uuid:item_id>/receive",
        MyStockReceiveView.as_view(),
        name="my-stock-receive",
    ),
    path(
        "me/turfs/<slug:slug>/stock/<uuid:item_id>/adjust",
        MyStockAdjustView.as_view(),
        name="my-stock-adjust",
    ),
    path(
        "me/turfs/<slug:slug>/stock/<uuid:item_id>/movements",
        MyStockMovementsView.as_view(),
        name="my-stock-movements",
    ),
    path("me/turfs/<slug:slug>/stock-log", MyMovementLogView.as_view(), name="my-stock-log"),
    # The counter
    path(
        "me/turfs/<slug:slug>/counter-sales",
        MyCounterSaleView.as_view(),
        name="my-counter-sales",
    ),
    path(
        "me/turfs/<slug:slug>/counter-sales/<uuid:sale_id>/void",
        MyCounterSaleVoidView.as_view(),
        name="my-counter-sale-void",
    ),
    # Rentals
    path("me/turfs/<slug:slug>/rentals", MyRentalListView.as_view(), name="my-rentals"),
    path(
        "me/turfs/<slug:slug>/rentals/<uuid:rental_id>/return",
        MyRentalSettleView.as_view(),
        name="my-rental-return",
    ),
    path(
        "me/turfs/<slug:slug>/rentals/<uuid:rental_id>/lost",
        MyRentalLostView.as_view(),
        name="my-rental-lost",
    ),
    # The platform warehouse
    path(
        "admin/warehouse/products",
        WarehouseProductListView.as_view(),
        name="warehouse-products",
    ),
    path("admin/warehouse/stock", WarehouseStockView.as_view(), name="warehouse-stock"),
    path(
        "admin/warehouse/stock/<uuid:item_id>/receive",
        WarehouseStockItemView.as_view(),
        name="warehouse-stock-receive",
    ),
]
