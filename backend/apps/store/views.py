"""Store endpoints: shopping, the cart, checkout, and the three order queues."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsPlatformAdmin
from apps.inventory.models import StockItem, StockLocation
from apps.inventory.services import OutOfStock, warehouse
from apps.matches.models import Match
from apps.turfs.selectors import turfs_for_staff
from apps.turfs.services import TURF_STAFF_ROLES, has_turf_role

from .models import Address, Order, RiderProfile
from .selectors import (
    my_orders,
    nearby_sources,
    next_match_for,
    open_orders,
    order_queryset,
    orders_for_turf,
    platform_orders,
    rider_orders,
    shoppable_stock,
)
from .serializers import (
    AddressSerializer,
    AddToCartSerializer,
    AssignRiderSerializer,
    CancelOrderSerializer,
    CartSerializer,
    CheckoutSerializer,
    OrderSerializer,
    RiderSerializer,
    SetCartQuantitySerializer,
    SettleOrderSerializer,
    StoreItemSerializer,
)
from .services import (
    accept_order,
    add_to_cart,
    assign_rider,
    cancel_order,
    cart_by_source,
    checkout,
    fulfilment_options,
    mark_out_for_delivery,
    mark_ready_for_pickup,
    pack_order,
    set_cart_quantity,
    settle_order,
)


def _error(exc: DjangoValidationError) -> Response:
    detail = exc.message_dict if hasattr(exc, "message_dict") else {"detail": exc.messages}
    code = status.HTTP_409_CONFLICT if isinstance(exc, OutOfStock) else status.HTTP_400_BAD_REQUEST
    return Response(detail, status=code)


def _int(value):
    try:
        return int(value)
    except TypeError, ValueError:
        return None


def _source_from(request, source_id: str | None) -> StockLocation:
    """A source by id, defaulting to the platform warehouse."""
    if not source_id or source_id == "platform":
        return warehouse()
    return get_object_or_404(StockLocation, id=source_id, is_active=True)


class StoreHomeView(APIView):
    """What the store leads with (DOMAIN §9): the player's next match, then nearby."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="store_home",
        summary="The store, arranged around this player",
        responses={200: None},
    )
    def get(self, request):
        match = next_match_for(request.user)
        sources = nearby_sources(user=request.user)

        match_turf_source = None
        if match is not None:
            match_turf_source = StockLocation.objects.filter(turf=match.turf).first()

        return Response(
            {
                "match": (
                    {
                        "id": str(match.id),
                        "sport": match.sport.name,
                        "turf_name": match.turf.name,
                        "turf_slug": match.turf.slug,
                        "starts_at": match.starts_at,
                        "source_id": str(match_turf_source.id) if match_turf_source else None,
                    }
                    if match is not None
                    else None
                ),
                "platform_source_id": str(warehouse().id),
                "sources": [
                    {
                        "id": str(source.id),
                        "name": source.name,
                        "turf_slug": source.turf.slug if source.turf_id else "",
                        "is_platform": source.turf_id is None,
                    }
                    for source in sources
                ],
            }
        )


class StoreProductsView(APIView):
    """What is for sale at one source, with the fitness filters."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="store_products",
        summary="Products at one source",
        parameters=[
            OpenApiParameter("source", str, description='Stock location id, or "platform".'),
            OpenApiParameter("category", str),
            OpenApiParameter("tag", str),
            OpenApiParameter("sport", str),
            OpenApiParameter("max_calories", int),
            OpenApiParameter("min_protein", int),
            OpenApiParameter("q", str),
        ],
        responses={200: StoreItemSerializer(many=True)},
    )
    def get(self, request):
        params = request.query_params
        source = _source_from(request, params.get("source"))
        items = shoppable_stock(
            location=source,
            category=params.get("category"),
            tag=params.get("tag"),
            sport=params.get("sport"),
            max_calories=_int(params.get("max_calories")),
            min_protein=_int(params.get("min_protein")),
            query=params.get("q"),
        )
        return Response(StoreItemSerializer(items, many=True).data)


class CartView(APIView):
    """The cart, already grouped the way it will be ordered."""

    permission_classes = [IsAuthenticated]

    def _payload(self, request, *, match=None, address=None) -> dict:
        groups = []
        subtotal = Decimal("0")
        count = 0

        for location, items in cart_by_source(user=request.user).items():
            group_subtotal = sum(
                (item.stock_item.price * item.quantity for item in items), Decimal("0")
            )
            subtotal += group_subtotal
            count += sum(item.quantity for item in items)
            options = fulfilment_options(
                user=request.user,
                location=location,
                items=items,
                match=match,
                address=address,
            )
            groups.append(
                {
                    "source_id": location.id,
                    "source_name": location.name,
                    "turf_slug": location.turf.slug if location.turf_id else "",
                    "is_platform": location.turf_id is None,
                    "items": items,
                    "subtotal": group_subtotal,
                    "options": [
                        {
                            "kind": option.kind,
                            "available": option.available,
                            "fee": option.fee,
                            "eta_hours": option.eta_hours,
                            "reason": option.reason,
                        }
                        for option in options
                    ],
                }
            )

        return {"groups": groups, "subtotal": subtotal, "item_count": count}

    @extend_schema(
        operation_id="cart_read",
        summary="My cart",
        parameters=[
            OpenApiParameter("match", str, description="Match id, to price delivery to a turf."),
            OpenApiParameter("address", str, description="Address id, to price delivery."),
        ],
        responses={200: CartSerializer},
    )
    def get(self, request):
        match = None
        if request.query_params.get("match"):
            match = Match.objects.filter(id=request.query_params["match"]).first()
        address = None
        if request.query_params.get("address"):
            address = Address.objects.filter(
                id=request.query_params["address"], player=request.user
            ).first()

        return Response(CartSerializer(self._payload(request, match=match, address=address)).data)

    @extend_schema(
        operation_id="cart_add",
        summary="Add to the cart",
        request=AddToCartSerializer,
        responses={200: CartSerializer, 409: None},
    )
    def post(self, request):
        payload = AddToCartSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        stock_item = get_object_or_404(
            StockItem.objects.select_related("product"),
            id=payload.validated_data["stock_item_id"],
        )
        try:
            add_to_cart(
                user=request.user,
                stock_item=stock_item,
                quantity=payload.validated_data["quantity"],
            )
        except DjangoValidationError as exc:
            return _error(exc)
        return Response(CartSerializer(self._payload(request)).data)

    @extend_schema(
        operation_id="cart_set_quantity",
        summary="Change or remove a line",
        request=SetCartQuantitySerializer,
        responses={200: CartSerializer, 409: None},
    )
    def patch(self, request):
        payload = SetCartQuantitySerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        stock_item = get_object_or_404(
            StockItem.objects.select_related("product"),
            id=payload.validated_data["stock_item_id"],
        )
        try:
            set_cart_quantity(
                user=request.user,
                stock_item=stock_item,
                quantity=payload.validated_data["quantity"],
            )
        except DjangoValidationError as exc:
            return _error(exc)
        return Response(CartSerializer(self._payload(request)).data)


class CheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="checkout",
        summary="Place the order(s)",
        description="One order per source. All or nothing.",
        request=CheckoutSerializer,
        responses={201: OrderSerializer(many=True), 409: None},
    )
    def post(self, request):
        payload = CheckoutSerializer(data=request.data)
        payload.is_valid(raise_exception=True)

        choices = {}
        for choice in payload.validated_data["choices"]:
            match = None
            if choice.get("match_id"):
                match = get_object_or_404(Match, id=choice["match_id"])
            address = None
            if choice.get("address_id"):
                address = get_object_or_404(Address, id=choice["address_id"], player=request.user)
            choices[str(choice["source_id"])] = {
                "fulfilment": choice["fulfilment"],
                "match": match,
                "address": address,
                "notes": choice.get("notes", ""),
            }

        try:
            orders = checkout(user=request.user, choices=choices)
        except DjangoValidationError as exc:
            return _error(exc)

        return Response(OrderSerializer(orders, many=True).data, status=status.HTTP_201_CREATED)


class AddressListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="addresses_list",
        summary="My addresses",
        responses={200: AddressSerializer(many=True)},
    )
    def get(self, request):
        return Response(
            AddressSerializer(Address.objects.filter(player=request.user), many=True).data
        )

    @extend_schema(
        operation_id="addresses_create",
        summary="Add an address",
        request=AddressSerializer,
        responses={201: AddressSerializer},
    )
    def post(self, request):
        payload = AddressSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        address = Address.objects.create(player=request.user, **payload.validated_data)
        if address.is_default:
            Address.objects.filter(player=request.user).exclude(id=address.id).update(
                is_default=False
            )
        return Response(AddressSerializer(address).data, status=status.HTTP_201_CREATED)


class MyOrderListView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="my_orders",
        summary="My orders",
        responses={200: OrderSerializer(many=True)},
    )
    def get(self, request):
        return Response(OrderSerializer(my_orders(request.user)[:50], many=True).data)


class OrderLookup:
    """Finding one order, for whoever is entitled to see it.

    A mixin, not a base view: inheriting the detail view would give every action a GET
    as well, which is eight operations sharing one id in the schema.
    """

    permission_classes = [IsAuthenticated]

    def _order(self, request, order_id) -> Order:
        order = get_object_or_404(order_queryset(), id=order_id)
        user = request.user
        if order.player_id == user.id:
            return order
        if order.rider_id and order.rider.user_id == user.id:
            return order
        from .services import can_manage

        if can_manage(order=order, user=user):
            return order
        # Not "forbidden": somebody else's order is none of their business and should
        # not even confirm it exists.
        self.permission_denied(request, message="No such order.")

    def act(self, request, order_id, action):
        """Run one transition and answer with the order as it now stands."""
        order = self._order(request, order_id)
        try:
            order = action(order)
        except DjangoValidationError as exc:
            return _error(exc)
        return Response(OrderSerializer(order).data)


class OrderDetailView(OrderLookup, APIView):
    """One order, for whoever is entitled to see it."""

    @extend_schema(
        operation_id="order_detail",
        summary="One order",
        responses={200: OrderSerializer},
    )
    def get(self, request, order_id):
        return Response(OrderSerializer(self._order(request, order_id)).data)


class OrderAcceptView(OrderLookup, APIView):
    @extend_schema(
        operation_id="order_accept",
        summary="Accept an order",
        request=None,
        responses={200: OrderSerializer},
    )
    def post(self, request, order_id):
        return self.act(
            request, order_id, lambda order: accept_order(order=order, actor=request.user)
        )


class OrderPackView(OrderLookup, APIView):
    @extend_schema(
        operation_id="order_pack",
        summary="Mark an order packed",
        request=None,
        responses={200: OrderSerializer},
    )
    def post(self, request, order_id):
        return self.act(
            request, order_id, lambda order: pack_order(order=order, actor=request.user)
        )


class OrderReadyView(OrderLookup, APIView):
    @extend_schema(
        operation_id="order_ready",
        summary="Ready for pickup",
        request=None,
        responses={200: OrderSerializer},
    )
    def post(self, request, order_id):
        return self.act(
            request, order_id, lambda order: mark_ready_for_pickup(order=order, actor=request.user)
        )


class OrderOutView(OrderLookup, APIView):
    @extend_schema(
        operation_id="order_out_for_delivery",
        summary="Out for delivery",
        request=None,
        responses={200: OrderSerializer},
    )
    def post(self, request, order_id):
        return self.act(
            request,
            order_id,
            lambda order: mark_out_for_delivery(order=order, actor=request.user),
        )


class OrderSettleView(OrderLookup, APIView):
    @extend_schema(
        operation_id="order_settle",
        summary="Delivered or picked up",
        request=SettleOrderSerializer,
        responses={200: OrderSerializer},
    )
    def post(self, request, order_id):
        payload = SettleOrderSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self.act(
            request,
            order_id,
            lambda order: settle_order(
                order=order,
                actor=request.user,
                cash_received=payload.validated_data.get("cash_received"),
            ),
        )


class OrderCancelView(OrderLookup, APIView):
    @extend_schema(
        operation_id="order_cancel",
        summary="Cancel an order",
        request=CancelOrderSerializer,
        responses={200: OrderSerializer},
    )
    def post(self, request, order_id):
        payload = CancelOrderSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        return self.act(
            request,
            order_id,
            lambda order: cancel_order(
                order=order, actor=request.user, reason=payload.validated_data.get("reason", "")
            ),
        )


class OrderAssignRiderView(OrderLookup, APIView):
    @extend_schema(
        operation_id="order_assign_rider",
        summary="Give it to a rider",
        request=AssignRiderSerializer,
        responses={200: OrderSerializer},
    )
    def post(self, request, order_id):
        payload = AssignRiderSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        rider = get_object_or_404(RiderProfile, id=payload.validated_data["rider_id"])
        return self.act(
            request,
            order_id,
            lambda order: assign_rider(order=order, rider=rider, actor=request.user),
        )


class TurfOrderQueueView(APIView):
    """A turf's incoming orders, next to its bookings."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="turf_orders",
        summary="Orders at my turf",
        parameters=[OpenApiParameter("all", bool, description="Include finished orders.")],
        responses={200: OrderSerializer(many=True)},
    )
    def get(self, request, slug):
        turf = get_object_or_404(turfs_for_staff(request.user), slug=slug)
        if not has_turf_role(turf=turf, user=request.user, roles=TURF_STAFF_ROLES):
            self.permission_denied(request, message="You are not staff at this turf.")

        orders = orders_for_turf(turf)
        if request.query_params.get("all") not in {"1", "true", "True"}:
            orders = open_orders(orders)
        return Response(OrderSerializer(orders[:100], many=True).data)


class PlatformOrderQueueView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    @extend_schema(
        operation_id="platform_orders",
        summary="The platform's order queue",
        parameters=[OpenApiParameter("all", bool)],
        responses={200: OrderSerializer(many=True)},
    )
    def get(self, request):
        orders = platform_orders()
        if request.query_params.get("all") not in {"1", "true", "True"}:
            orders = open_orders(orders)
        return Response(OrderSerializer(orders[:100], many=True).data)


class RiderListView(APIView):
    permission_classes = [IsAuthenticated, IsPlatformAdmin]

    @extend_schema(
        operation_id="riders_list",
        summary="Riders",
        responses={200: RiderSerializer(many=True)},
    )
    def get(self, request):
        return Response(
            RiderSerializer(
                RiderProfile.objects.filter(is_active=True).select_related("user"), many=True
            ).data
        )


class MyDeliveriesView(APIView):
    """A rider's own list — never the whole queue."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="my_deliveries",
        summary="Deliveries assigned to me",
        responses={200: OrderSerializer(many=True)},
    )
    def get(self, request):
        rider = getattr(request.user, "rider_profile", None)
        if rider is None:
            return Response([])
        return Response(OrderSerializer(open_orders(rider_orders(rider)), many=True).data)
