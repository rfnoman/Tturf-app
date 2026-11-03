from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    is_read = serializers.BooleanField(read_only=True)

    class Meta:
        model = Notification
        fields = ["id", "kind", "title", "body", "url", "data", "is_read", "created_at"]
        read_only_fields = fields


class MarkReadSerializer(serializers.Serializer):
    ids = serializers.ListField(
        child=serializers.UUIDField(),
        required=False,
        help_text="Omit to mark everything read.",
    )
