"""Inventory, counter and rental endpoints (DOMAIN §9).

Three audiences, three shapes of route:

* `/me/turfs/{slug}/…` — a turf's own staff, managing their shelf and selling from it.
* `/admin/warehouse/…` — the platform's stock, for the Phase 08 store.
* `/turfs/{slug}/products` and `/store/products` — public reads, which is what the store
  and the match page will use.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.bookings.models import Booking
from apps.core.permissions import IsPlatformAdmin
from apps.matches.models import Match
from apps.players.models import PlayerProfile
from apps.sports.models import Sport
from apps.turfs.selectors import public_turfs, turfs_for_staff
from apps.turfs.services import TURF_EDIT_ROLES, TURF_STAFF_ROLES, has_turf_role

from .models import CounterSale, OwnerType, Product, Rental, StockItem
from .selectors import (
    counter_sales_for,
    movements_for,
    product_catalogue,
    rentals_for,
    stock_for,
)
from .serializers import (
    AdjustStockSerializer,
    CounterSaleSerializer,
    CounterSaleWriteSerializer,
    ProductCategorySerializer,
    ProductSerializer,
    ProductWriteSerializer,
    ReceiveStockSerializer,
    RentalSerializer,
    RentOutSerializer,
    SettleRentalSerializer,
    StockItemSerializer,
    StockItemWriteSerializer,
    StockMovementSerializer,
    VoidSaleSerializer,
)
from .services import (
    OutOfStock,
    adjust_stock,
    get_or_create_item,
    location_for_turf,
    mark_rental_lost,
    receive_stock,
    record_counter_sale,
    rent_out,
    return_rental,
    void_counter_sale,
    warehouse,
)


def _error(exc: DjangoValidationError) -> Response:
    detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
    # Out of stock is not a malformed request — somebody else got there first.
    code = status.HTTP_409_CONFLICT if isinstance(exc, OutOfStock) else status.HTTP_400_BAD_REQUEST
    return Response(detail, status=code)


def _unique_slug(*, name: str, turf) -> str:
    """A slug unique within its owner, so two turfs can both sell "Banana"."""
    base = slugify(name)[:130] or "product"
    candidate = base
    index = 2
    while Product.objects.filter(turf=turf, slug=candidate).exists():
        candidate = f"{base}-{index}"
        index += 1
    return candidate


class TurfScopedView(APIView):
    """A turf from the URL, with this reader's role checked once."""

    permission_classes = [IsAuthenticated]
    #: Roles allowed to write here. Reads only need staff.
    write_roles = TURF_EDIT_ROLES

    def get_turf(self, request, slug, *, write: bool):
        turf = get_object_or_404(turfs_for_staff(request.user), slug=slug)
        roles = self.write_roles if write else TURF_STAFF_ROLES
        if not has_turf_role(turf=turf, user=request.user, roles=roles):
            self.permission_denied(request, message="You cannot do that at this turf.")
        return turf


# ---------------------------------------------------------------------------
# Public reads
# ---------------------------------------------------------------------------
class ProductCategoryListView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="product_categories",
        summary="Product categories",
        responses={200: ProductCategorySerializer(many=True)},
    )
    def get(self, request):
        from .models import ProductCategory

        return Response(ProductCategorySerializer(ProductCategory.objects.all(), many=True).data)


class TurfProductListView(APIView):
    """What a turf sells, for anybody looking at the turf (Phase 08 reads this)."""

    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="turf_products",
        summary="A turf's products",
        parameters=[
            OpenApiParameter("category", str),
            OpenApiParameter("tag", str),
            OpenApiParameter("kind", str, description="sale | rental"),
        ],
        responses={200: ProductSerializer(many=True)},
    )
    def get(self, request, slug):
        turf = get_object_or_404(public_turfs(), slug=slug)
        products = product_catalogue(
            turf=turf,
            category=request.query_params.get("category"),
            tag=request.query_params.get("tag"),
            kind=request.query_params.get("kind"),
        )
        return Response(ProductSerializer(products, many=True).data)


class PlatformProductListView(APIView):
    """The platform catalogue — the store's own shelf."""

    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="platform_products",
        summary="Platform products",
        parameters=[
            OpenApiParameter("category", str),
            OpenApiParameter("tag", str),
            OpenApiParameter("sport", str),
        ],
        responses={200: ProductSerializer(many=True)},
    )
    def get(self, request):
        products = product_catalogue(
            turf=None,
            category=request.query_params.get("category"),
            tag=request.query_params.get("tag"),
            sport=request.query_params.get("sport"),
        )
        return Response(ProductSerializer(products, many=True).data)


# ---------------------------------------------------------------------------
# A turf's own products
# ---------------------------------------------------------------------------
class MyProductListView(TurfScopedView):
    @extend_schema(
        operation_id="my_products_list",
        summary="Products at my turf",
        responses={200: ProductSerializer(many=True)},
    )
    def get(self, request, slug):
        turf = self.get_turf(request, slug, write=False)
        # Staff see what is switched off too; the public list does not.
        return Response(
            ProductSerializer(
                Product.objects.filter(turf=turf)
                .select_related("category")
                .prefetch_related("sports"),
                many=True,
            ).data
        )

    @extend_schema(
        operation_id="my_products_create",
        summary="Add a product",
        request=ProductWriteSerializer,
        responses={201: ProductSerializer},
    )
    def post(self, request, slug):
        turf = self.get_turf(request, slug, write=True)
        payload = ProductWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        data = dict(payload.validated_data)
        sports = data.pop("sports", [])
        product = Product.objects.create(
            owner_type=OwnerType.TURF,
            turf=turf,
            slug=_unique_slug(name=data["name"], turf=turf),
            **data,
        )
        if sports:
            product.sports.set(Sport.objects.filter(slug__in=sports))

        # A product with no stock row is invisible on the stock screen, which reads as a
        # bug the first time somebody adds one.
        get_or_create_item(location=location_for_turf(turf), product=product)
        return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)


class MyProductDetailView(TurfScopedView):
    @extend_schema(
        operation_id="my_products_update",
        summary="Update a product",
        request=ProductWriteSerializer,
        responses={200: ProductSerializer},
    )
    def patch(self, request, slug, product_id):
        turf = self.get_turf(request, slug, write=True)
        product = get_object_or_404(Product, id=product_id, turf=turf)

        payload = ProductWriteSerializer(product, data=request.data, partial=True)
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)
        sports = data.pop("sports", None)

        for field, value in data.items():
            setattr(product, field, value)
        product.save()
        if sports is not None:
            product.sports.set(Sport.objects.filter(slug__in=sports))

        return Response(ProductSerializer(product).data)

    @extend_schema(
        operation_id="my_products_delete",
        summary="Retire a product",
        description="Deactivated rather than deleted: past sales point at it.",
        responses={204: None},
    )
    def delete(self, request, slug, product_id):
        turf = self.get_turf(request, slug, write=True)
        product = get_object_or_404(Product, id=product_id, turf=turf)
        product.is_active = False
        product.save(update_fields=["is_active", "updated_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Stock
# ---------------------------------------------------------------------------
class MyStockListView(TurfScopedView):
    @extend_schema(
        operation_id="my_stock_list",
        summary="Stock at my turf",
        parameters=[OpenApiParameter("low", bool, description="Only what needs restocking.")],
        responses={200: StockItemSerializer(many=True)},
    )
    def get(self, request, slug):
        turf = self.get_turf(request, slug, write=False)
        items = stock_for(
            location=location_for_turf(turf),
            low_only=request.query_params.get("low") in {"1", "true", "True"},
        )
        return Response(StockItemSerializer(items, many=True).data)


class StockItemLookup:
    """Finding one stock item at the caller's turf.

    A mixin rather than a base view: inheriting a view would inherit its HTTP methods
    too, and `receive` would then also answer PATCH — which drf-spectacular rightly
    reports as four operations sharing one id.
    """

    def _item(self, request, slug, item_id, *, write: bool) -> StockItem:
        turf = self.get_turf(request, slug, write=write)
        return get_object_or_404(
            StockItem.objects.select_related("product", "location"),
            id=item_id,
            location__turf=turf,
        )


class MyStockItemView(StockItemLookup, TurfScopedView):
    @extend_schema(
        operation_id="my_stock_update",
        summary="Set this location's price or threshold",
        request=StockItemWriteSerializer,
        responses={200: StockItemSerializer},
    )
    def patch(self, request, slug, item_id):
        item = self._item(request, slug, item_id, write=True)
        payload = StockItemWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        for field, value in payload.validated_data.items():
            setattr(item, field, value)
        item.save()
        return Response(StockItemSerializer(item).data)


class MyStockReceiveView(StockItemLookup, TurfScopedView):
    @extend_schema(
        operation_id="my_stock_receive",
        summary="Receive stock",
        request=ReceiveStockSerializer,
        responses={200: StockItemSerializer},
    )
    def post(self, request, slug, item_id):
        item = self._item(request, slug, item_id, write=True)
        payload = ReceiveStockSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            item = receive_stock(
                item=item,
                quantity=payload.validated_data["quantity"],
                actor=request.user,
                note=payload.validated_data.get("note", ""),
            )
        except DjangoValidationError as exc:
            return _error(exc)
        return Response(StockItemSerializer(item).data)


class MyStockAdjustView(StockItemLookup, TurfScopedView):
    @extend_schema(
        operation_id="my_stock_adjust",
        summary="Adjust stock, with a reason",
        request=AdjustStockSerializer,
        responses={200: StockItemSerializer},
    )
    def post(self, request, slug, item_id):
        item = self._item(request, slug, item_id, write=True)
        payload = AdjustStockSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            item = adjust_stock(
                item=item,
                delta=payload.validated_data["delta"],
                reason=payload.validated_data["reason"],
                actor=request.user,
            )
        except DjangoValidationError as exc:
            return _error(exc)
        return Response(StockItemSerializer(item).data)


class MyStockMovementsView(StockItemLookup, TurfScopedView):
    @extend_schema(
        operation_id="my_stock_movements",
        summary="The movement log",
        responses={200: StockMovementSerializer(many=True)},
    )
    def get(self, request, slug, item_id):
        item = self._item(request, slug, item_id, write=False)
        return Response(StockMovementSerializer(movements_for(item=item), many=True).data)


class MyMovementLogView(TurfScopedView):
    @extend_schema(
        operation_id="my_stock_log",
        summary="Everything that moved at my turf",
        responses={200: StockMovementSerializer(many=True)},
    )
    def get(self, request, slug):
        turf = self.get_turf(request, slug, write=False)
        return Response(
            StockMovementSerializer(movements_for(location=location_for_turf(turf)), many=True).data
        )


# ---------------------------------------------------------------------------
# The counter
# ---------------------------------------------------------------------------
class MyCounterSaleView(TurfScopedView):
    # A cashier exists to ring up sales, so this is the one place they may write.
    write_roles = TURF_STAFF_ROLES

    @extend_schema(
        operation_id="counter_sales_list",
        summary="Today's counter sales",
        responses={200: CounterSaleSerializer(many=True)},
    )
    def get(self, request, slug):
        turf = self.get_turf(request, slug, write=False)
        return Response(CounterSaleSerializer(counter_sales_for(turf=turf), many=True).data)

    @extend_schema(
        operation_id="counter_sale_create",
        summary="Ring up a sale",
        request=CounterSaleWriteSerializer,
        responses={201: CounterSaleSerializer, 409: None},
    )
    def post(self, request, slug):
        turf = self.get_turf(request, slug, write=True)
        payload = CounterSaleWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        products = {
            str(product.id): product
            for product in Product.objects.filter(
                turf=turf, id__in=[line["product_id"] for line in data["lines"]]
            )
        }
        lines = []
        for line in data["lines"]:
            product = products.get(str(line["product_id"]))
            if product is None:
                return Response(
                    {"lines": "That product is not on this turf's shelf."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            lines.append({"product": product, "quantity": line["quantity"]})

        booking = None
        if data.get("booking_id"):
            booking = get_object_or_404(Booking, id=data["booking_id"], ground__turf=turf)

        try:
            sale = record_counter_sale(
                turf=turf,
                staff=request.user,
                lines=lines,
                cash_received=data.get("cash_received"),
                customer_phone=data.get("customer_phone", ""),
                booking=booking,
                note=data.get("note", ""),
            )
        except DjangoValidationError as exc:
            return _error(exc)

        return Response(CounterSaleSerializer(sale).data, status=status.HTTP_201_CREATED)


class MyCounterSaleVoidView(TurfScopedView):
    write_roles = TURF_STAFF_ROLES

    @extend_schema(
        operation_id="counter_sale_void",
        summary="Void a sale",
        request=VoidSaleSerializer,
        responses={200: CounterSaleSerializer},
    )
    def post(self, request, slug, sale_id):
        turf = self.get_turf(request, slug, write=True)
        sale = get_object_or_404(CounterSale, id=sale_id, turf=turf)
        payload = VoidSaleSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            sale = void_counter_sale(
                sale=sale, actor=request.user, reason=payload.validated_data.get("reason", "")
            )
        except DjangoValidationError as exc:
            return _error(exc)
        return Response(CounterSaleSerializer(sale).data)


# ---------------------------------------------------------------------------
# Rentals
# ---------------------------------------------------------------------------
class MyRentalListView(TurfScopedView):
    write_roles = TURF_STAFF_ROLES

    @extend_schema(
        operation_id="rentals_list",
        summary="Rentals at my turf",
        parameters=[
            OpenApiParameter("status", str, description="reserved | out | returned | lost")
        ],
        responses={200: RentalSerializer(many=True)},
    )
    def get(self, request, slug):
        turf = self.get_turf(request, slug, write=False)
        return Response(
            RentalSerializer(
                rentals_for(turf=turf, status=request.query_params.get("status")), many=True
            ).data
        )

    @extend_schema(
        operation_id="rental_out",
        summary="Hand gear over",
        request=RentOutSerializer,
        responses={201: RentalSerializer, 409: None},
    )
    def post(self, request, slug):
        turf = self.get_turf(request, slug, write=True)
        payload = RentOutSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = payload.validated_data

        product = get_object_or_404(Product, id=data["product_id"], turf=turf)
        player = get_object_or_404(
            PlayerProfile.objects.select_related("user"), id=data["player_id"]
        ).user
        match = get_object_or_404(Match, id=data["match_id"]) if data.get("match_id") else None
        booking = (
            get_object_or_404(Booking, id=data["booking_id"], ground__turf=turf)
            if data.get("booking_id")
            else None
        )

        try:
            rental = rent_out(
                turf=turf,
                product=product,
                player=player,
                quantity=data.get("quantity", 1),
                actor=request.user,
                match=match,
                booking=booking,
            )
        except DjangoValidationError as exc:
            return _error(exc)

        return Response(RentalSerializer(rental).data, status=status.HTTP_201_CREATED)


class RentalLookup:
    """Finding one rental at the caller's turf — a mixin, for the reason above."""

    write_roles = TURF_STAFF_ROLES

    def _rental(self, request, slug, rental_id) -> Rental:
        turf = self.get_turf(request, slug, write=True)
        return get_object_or_404(Rental.objects.select_related("product"), id=rental_id, turf=turf)


class MyRentalSettleView(RentalLookup, TurfScopedView):
    @extend_schema(
        operation_id="rental_return",
        summary="Gear came back",
        request=SettleRentalSerializer,
        responses={200: RentalSerializer},
    )
    def post(self, request, slug, rental_id):
        rental = self._rental(request, slug, rental_id)
        payload = SettleRentalSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            rental = return_rental(
                rental=rental, actor=request.user, charges=payload.validated_data.get("charges")
            )
        except DjangoValidationError as exc:
            return _error(exc)
        return Response(RentalSerializer(rental).data)


class MyRentalLostView(RentalLookup, TurfScopedView):
    @extend_schema(
        operation_id="rental_lost",
        summary="Gear did not come back",
        request=SettleRentalSerializer,
        responses={200: RentalSerializer},
    )
    def post(self, request, slug, rental_id):
        rental = self._rental(request, slug, rental_id)
        payload = SettleRentalSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            rental = mark_rental_lost(
                rental=rental, actor=request.user, charges=payload.validated_data.get("charges")
            )
        except DjangoValidationError as exc:
            return _error(exc)
        return Response(RentalSerializer(rental).data)


# ---------------------------------------------------------------------------
# The platform warehouse
# ---------------------------------------------------------------------------
class WarehouseProductListView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    @extend_schema(
        operation_id="warehouse_products_list",
        summary="Platform products",
        responses={200: ProductSerializer(many=True)},
    )
    def get(self, request):
        return Response(
            ProductSerializer(
                Product.objects.filter(owner_type=OwnerType.PLATFORM)
                .select_related("category")
                .prefetch_related("sports"),
                many=True,
            ).data
        )

    @extend_schema(
        operation_id="warehouse_products_create",
        summary="Add a platform product",
        request=ProductWriteSerializer,
        responses={201: ProductSerializer},
    )
    def post(self, request):
        payload = ProductWriteSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        data = dict(payload.validated_data)
        sports = data.pop("sports", [])

        product = Product.objects.create(
            owner_type=OwnerType.PLATFORM,
            turf=None,
            slug=_unique_slug(name=data["name"], turf=None),
            **data,
        )
        if sports:
            product.sports.set(Sport.objects.filter(slug__in=sports))
        get_or_create_item(location=warehouse(), product=product)
        return Response(ProductSerializer(product).data, status=status.HTTP_201_CREATED)


class WarehouseStockView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    @extend_schema(
        operation_id="warehouse_stock",
        summary="Warehouse stock",
        responses={200: StockItemSerializer(many=True)},
    )
    def get(self, request):
        return Response(StockItemSerializer(stock_for(location=warehouse()), many=True).data)


class WarehouseStockItemView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    @extend_schema(
        operation_id="warehouse_stock_receive",
        summary="Receive warehouse stock",
        request=ReceiveStockSerializer,
        responses={200: StockItemSerializer},
    )
    def post(self, request, item_id):
        item = get_object_or_404(StockItem, id=item_id, location=warehouse())
        payload = ReceiveStockSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        try:
            item = receive_stock(
                item=item,
                quantity=payload.validated_data["quantity"],
                actor=request.user,
                note=payload.validated_data.get("note", ""),
            )
        except DjangoValidationError as exc:
            return _error(exc)
        return Response(StockItemSerializer(item).data)
