from __future__ import annotations

import json
import logging

from django.conf import settings
from drf_spectacular.utils import OpenApiExample, extend_schema, inline_serializer
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from svix.webhooks import Webhook, WebhookVerificationError

from apps.core.throttling import WebhookThrottle

from .serializers import UserSerializer
from .services import deactivate_user_from_clerk, sync_user_from_clerk

logger = logging.getLogger(__name__)

SVIX_HEADERS = ("svix-id", "svix-timestamp", "svix-signature")


class MeView(APIView):
    """The authenticated user, as Django knows them."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="me",
        summary="Current user",
        responses={200: UserSerializer},
    )
    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ClerkWebhookView(APIView):
    """Receive Clerk user events.

    Signature verification is mandatory: the body is untrusted until svix has checked
    it against the endpoint's signing secret (svix also enforces a 5-minute timestamp
    window, which is what stops replays).
    """

    authentication_classes: list = []
    # A scope of its own: without one this would share the anonymous bucket with every
    # signed-out visitor, and a burst of user updates would start being dropped.
    throttle_classes = [WebhookThrottle]
    permission_classes = [AllowAny]

    @extend_schema(
        operation_id="clerk_webhook",
        summary="Clerk webhook receiver",
        description=(
            "Handles `user.created`, `user.updated` and `user.deleted`. Verified with "
            "svix using `CLERK_WEBHOOK_SIGNING_SECRET`."
        ),
        request=None,
        responses={
            200: inline_serializer(
                name="WebhookAccepted",
                fields={
                    "status": serializers.CharField(),
                    "event": serializers.CharField(allow_null=True),
                },
            ),
            400: inline_serializer(
                name="WebhookRejected",
                fields={"detail": serializers.CharField()},
            ),
        },
        examples=[
            OpenApiExample(
                "user.created",
                value={"status": "ok", "event": "user.created"},
                response_only=True,
            )
        ],
    )
    def post(self, request):
        secret = settings.CLERK_WEBHOOK_SIGNING_SECRET
        if not secret:
            logger.error("CLERK_WEBHOOK_SIGNING_SECRET is not set; rejecting webhook.")
            return Response(
                {"detail": "Webhook receiver is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        headers = {name: request.headers.get(name, "") for name in SVIX_HEADERS}
        if not all(headers.values()):
            return Response(
                {"detail": "Missing svix signature headers."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            # svix must see the raw body, byte for byte. `verify` raises on failure and
            # returns nothing, so the body is parsed below — only once it is trusted.
            Webhook(secret).verify(request.body, headers)
        except WebhookVerificationError:
            logger.warning("Rejected Clerk webhook with an invalid signature.")
            return Response(
                {"detail": "Invalid webhook signature."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return Response(
                {"detail": "Body is not valid JSON."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(payload, dict):
            return Response(
                {"detail": "Body is not a webhook event object."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        event_type = payload.get("type")
        data = payload.get("data") or {}
        handled = self.handle_event(event_type, data, svix_id=headers["svix-id"])
        return Response({"status": "ok" if handled else "ignored", "event": event_type})

    def handle_event(self, event_type: str | None, data: dict, *, svix_id: str) -> bool:
        """Dispatch a verified event. Returns False for events we do not act on."""
        try:
            match event_type:
                case "user.created" | "user.updated":
                    sync_user_from_clerk(data)
                case "user.deleted":
                    deactivate_user_from_clerk(data)
                case _:
                    logger.info(
                        "Ignoring unhandled Clerk event",
                        extra={"event": event_type, "svix_id": svix_id},
                    )
                    return False
        except ValueError as exc:
            # A malformed payload is the sender's problem, but retrying will not help,
            # so log it and acknowledge rather than make Clerk retry forever.
            logger.error(
                "Malformed Clerk payload: %s",
                exc,
                extra={"event": event_type, "svix_id": svix_id},
            )
            return False
        return True
