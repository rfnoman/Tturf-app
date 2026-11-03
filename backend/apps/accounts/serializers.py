from rest_framework import serializers

from .models import User


class UserSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id",
            "clerk_id",
            "email",
            "phone",
            "first_name",
            "last_name",
            "full_name",
            "image_url",
            "is_platform_admin",
            "is_active",
            "created_at",
        ]
        read_only_fields = fields
