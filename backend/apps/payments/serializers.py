from rest_framework import serializers

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    collected_by_name = serializers.CharField(
        source="collected_by.full_name", read_only=True, default=""
    )
    method_label = serializers.CharField(source="get_method_display", read_only=True)

    class Meta:
        model = Payment
        fields = [
            "id",
            "method",
            "method_label",
            "amount",
            "status",
            "collected_by_name",
            "collected_at",
            "reference",
            "note",
            "created_at",
        ]
        read_only_fields = fields
