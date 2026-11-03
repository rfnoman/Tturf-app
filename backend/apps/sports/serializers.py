from __future__ import annotations

from rest_framework import serializers

from .models import (
    Attribute,
    Sport,
    SportAttributeWeight,
    SportFormat,
    SportProposal,
    SportSkill,
    StatDefinition,
)


class AttributeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attribute
        fields = ["id", "key", "label", "description", "order"]


class SportFormatSerializer(serializers.ModelSerializer):
    capacity = serializers.IntegerField(read_only=True)

    class Meta:
        model = SportFormat
        fields = ["id", "name", "slug", "players_per_side", "capacity", "order"]


class SportSkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = SportSkill
        fields = [
            "id",
            "key",
            "label",
            "description",
            "weight",
            "counts_toward_overall",
            "order",
        ]


class SportAttributeWeightSerializer(serializers.ModelSerializer):
    attribute = AttributeSerializer(read_only=True)

    class Meta:
        model = SportAttributeWeight
        fields = ["id", "attribute", "weight"]


class StatDefinitionSerializer(serializers.ModelSerializer):
    class Meta:
        model = StatDefinition
        fields = [
            "id",
            "key",
            "label",
            "value_type",
            "scope",
            "min_value",
            "max_value",
            "unit",
            "is_positive",
            "show_on_profile",
            "order",
        ]


class SportSerializer(serializers.ModelSerializer):
    """The full catalogue entry: one request feeds the whole onboarding wizard."""

    formats = SportFormatSerializer(many=True, read_only=True)
    skills = SportSkillSerializer(many=True, read_only=True)
    attribute_weights = SportAttributeWeightSerializer(many=True, read_only=True)
    stat_definitions = StatDefinitionSerializer(many=True, read_only=True)
    # Declared explicitly so the OpenAPI schema says `string[]` rather than `unknown`;
    # a bare JSONField would leave the generated frontend type unusable.
    positions = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = Sport
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "icon",
            "met_value",
            "positions",
            "is_active",
            "order",
            "formats",
            "skills",
            "attribute_weights",
            "stat_definitions",
        ]


class SportSummarySerializer(serializers.ModelSerializer):
    """Just enough to label a sport elsewhere (profile cards, match board, orders)."""

    # Blank is a legitimate value but the schema must not make it optional, or every
    # consumer has to narrow `string | undefined` before rendering.
    icon = serializers.CharField(read_only=True, allow_blank=True)

    class Meta:
        model = Sport
        fields = ["id", "name", "slug", "icon"]


class SportProposalSerializer(serializers.ModelSerializer):
    merged_into = SportSummarySerializer(read_only=True)
    proposed_by_name = serializers.CharField(source="proposed_by.full_name", read_only=True)

    class Meta:
        model = SportProposal
        fields = [
            "id",
            "name",
            "description",
            "status",
            "merged_into",
            "review_note",
            "reviewed_at",
            "proposed_by_name",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "status",
            "merged_into",
            "review_note",
            "reviewed_at",
            "proposed_by_name",
            "created_at",
        ]


class SportProposalCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=80)
    description = serializers.CharField(max_length=2000, allow_blank=True, required=False)


class SportProposalApproveSerializer(serializers.Serializer):
    """Admins may tidy the name and set the MET value as they approve."""

    name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    icon = serializers.CharField(max_length=32, required=False, allow_blank=True)
    met_value = serializers.DecimalField(
        max_digits=4, decimal_places=2, required=False, min_value=0
    )
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True)


class SportProposalMergeSerializer(serializers.Serializer):
    sport_id = serializers.UUIDField()
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True)

    def validate_sport_id(self, value):
        if not Sport.objects.filter(id=value).exists():
            raise serializers.ValidationError("No such sport.")
        return value


class SportProposalRejectSerializer(serializers.Serializer):
    note = serializers.CharField(max_length=2000)
