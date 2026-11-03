from __future__ import annotations

from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Notification
from .selectors import inbox
from .serializers import MarkReadSerializer, NotificationSerializer
from .services import mark_read, unread_count


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """The notification centre. Scoped to the caller — there is no cross-user read."""

    serializer_class = NotificationSerializer
    permission_classes = [IsAuthenticated]
    queryset = Notification.objects.none()

    def get_queryset(self):
        unread_only = self.request.query_params.get("unread") in {"1", "true", "True"}
        return inbox(self.request.user, unread_only=unread_only)

    @extend_schema(
        operation_id="my_notifications_list",
        summary="My notifications",
        parameters=[OpenApiParameter("unread", bool, description="Only unread ones.")],
    )
    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)

    @extend_schema(
        operation_id="my_notifications_unread_count",
        summary="Unread count",
        description="What the bell badge shows. Cheap enough to poll.",
        responses={
            200: inline_serializer(
                name="UnreadCount", fields={"unread": serializers.IntegerField()}
            )
        },
    )
    @action(detail=False, methods=["get"], url_path="unread-count", pagination_class=None)
    def unread_count(self, request):
        return Response({"unread": unread_count(user=request.user)})

    @extend_schema(
        operation_id="my_notifications_read",
        summary="Mark notifications read",
        request=MarkReadSerializer,
        responses={
            200: inline_serializer(name="MarkedRead", fields={"marked": serializers.IntegerField()})
        },
    )
    @action(detail=False, methods=["post"], pagination_class=None)
    def read(self, request):
        payload = MarkReadSerializer(data=request.data)
        payload.is_valid(raise_exception=True)
        ids = payload.validated_data.get("ids")
        return Response({"marked": mark_read(user=request.user, ids=ids)})
