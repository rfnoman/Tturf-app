from __future__ import annotations

from django.conf import settings
from rest_framework import serializers

from apps.sports.models import Sport
from apps.sports.serializers import SportSummarySerializer

from .models import RATING_MAX, RATING_MIN, PlayerProfile, PlayerSport, PlayerSportRating


class PlayerAttributeSerializer(serializers.Serializer):
    """Flattened for the card: the UI wants a key, a label and a number."""

    key = serializers.CharField(source="attribute.key")
    label = serializers.CharField(source="attribute.display_label")
    value = serializers.IntegerField()
    source = serializers.CharField()


class PlayerSkillSerializer(serializers.Serializer):
    key = serializers.CharField(source="sport_skill.key")
    label = serializers.CharField(source="sport_skill.display_label")
    value = serializers.IntegerField()
    source = serializers.CharField()
    counts_toward_overall = serializers.BooleanField(source="sport_skill.counts_toward_overall")


class PlayerSportCardSerializer(serializers.Serializer):
    """One FIFA-style card: a sport, the overall, positions and the six key skills.

    Assembled in ``selectors.player_sport_cards`` rather than read off a single model,
    because a card spans ``PlayerSport``, ``PlayerSportRating`` and ``PlayerSkill``.
    """

    sport = SportSummarySerializer()
    positions = serializers.ListField(child=serializers.CharField())
    overall = serializers.IntegerField()
    is_provisional = serializers.BooleanField()
    is_verified = serializers.BooleanField()
    matches_played = serializers.IntegerField()
    wins = serializers.IntegerField()
    draws = serializers.IntegerField()
    losses = serializers.IntegerField()
    motm_awards = serializers.IntegerField()
    skills = PlayerSkillSerializer(many=True)


class PlayerProfileSerializer(serializers.ModelSerializer):
    """The public player card (DOMAIN §3)."""

    name = serializers.CharField(read_only=True)
    photo_url = serializers.CharField(read_only=True)
    weight_is_estimated = serializers.BooleanField(read_only=True)
    attributes = PlayerAttributeSerializer(many=True, read_only=True)
    sport_cards = PlayerSportCardSerializer(many=True, read_only=True)

    class Meta:
        model = PlayerProfile
        fields = [
            "id",
            "name",
            "display_name",
            "photo_url",
            "date_of_birth",
            "gender",
            "height_cm",
            "weight_kg",
            "weight_is_estimated",
            "area",
            "preferred_side",
            "bio",
            "discoverable",
            "reliability_score",
            "onboarding_completed",
            "attributes",
            "sport_cards",
            "created_at",
        ]
        read_only_fields = fields


class PublicPlayerProfileSerializer(PlayerProfileSerializer):
    """What other players may see: no contact details, no exact date of birth.

    Age is derived instead of exposing the date itself, and ``discoverable`` is dropped
    because it is nobody else's business.
    """

    age = serializers.SerializerMethodField()

    class Meta(PlayerProfileSerializer.Meta):
        fields = [
            field
            for field in PlayerProfileSerializer.Meta.fields
            if field not in {"date_of_birth", "discoverable", "weight_kg", "weight_is_estimated"}
        ] + ["age"]
        read_only_fields = fields

    def get_age(self, obj) -> int | None:
        if not obj.date_of_birth:
            return None
        from apps.core.utils import now

        today = now().date()
        born = obj.date_of_birth
        return today.year - born.year - ((today.month, today.day) < (born.month, born.day))


class AttributeValuesField(serializers.DictField):
    """``{attribute_key: 1-99}``. Values are capped again in the service."""

    child = serializers.IntegerField(min_value=RATING_MIN, max_value=RATING_MAX)


class SkillValuesField(serializers.DictField):
    child = serializers.IntegerField(min_value=RATING_MIN, max_value=RATING_MAX)


class OnboardingSportSerializer(serializers.Serializer):
    sport = serializers.SlugField()
    positions = serializers.ListField(
        child=serializers.CharField(max_length=40), required=False, default=list
    )
    skills = SkillValuesField(required=False, default=dict)


class OnboardingSerializer(serializers.Serializer):
    """The wizard payload. Field-level validation only; rules live in the service."""

    display_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    date_of_birth = serializers.DateField(required=False, allow_null=True)
    gender = serializers.ChoiceField(
        choices=PlayerProfile.Gender.choices, required=False, allow_blank=True
    )
    height_cm = serializers.IntegerField(min_value=80, max_value=260, required=False)
    weight_kg = serializers.DecimalField(
        max_digits=5, decimal_places=1, min_value=20, max_value=300, required=False
    )
    area = serializers.CharField(max_length=80, required=False, allow_blank=True)
    preferred_side = serializers.ChoiceField(
        choices=PlayerProfile.PreferredSide.choices, required=False, allow_blank=True
    )
    bio = serializers.CharField(max_length=500, required=False, allow_blank=True)
    discoverable = serializers.BooleanField(required=False)
    attributes = AttributeValuesField(required=False, default=dict)
    sports = OnboardingSportSerializer(many=True)

    def validate_sports(self, value):
        if not value:
            raise serializers.ValidationError("Choose at least one sport.")
        slugs = [entry["sport"] for entry in value]
        if len(slugs) != len(set(slugs)):
            raise serializers.ValidationError("A sport can only be chosen once.")
        return value


class ProfileUpdateSerializer(serializers.ModelSerializer):
    """PATCH /me/profile. Attributes may be re-assessed from the settings page."""

    attributes = AttributeValuesField(required=False)

    class Meta:
        model = PlayerProfile
        fields = [
            "display_name",
            "photo",
            "date_of_birth",
            "gender",
            "height_cm",
            "weight_kg",
            "area",
            "preferred_side",
            "bio",
            "discoverable",
            "attributes",
        ]
        extra_kwargs = {
            "weight_kg": {
                "help_text": (
                    "Optional. Used only for calorie estimates; without it "
                    f"{settings.DEFAULT_PLAYER_WEIGHT_KG} kg is assumed and the estimate "
                    "is flagged."
                )
            }
        }


class PlayerSportWriteSerializer(serializers.Serializer):
    sport = serializers.SlugField()
    positions = serializers.ListField(
        child=serializers.CharField(max_length=40), required=False, default=list
    )
    skills = SkillValuesField(required=False, default=dict)

    def validate_sport(self, value):
        if not Sport.objects.filter(slug=value, is_active=True).exists():
            raise serializers.ValidationError("No such active sport.")
        return value


class PlayerSportSerializer(serializers.ModelSerializer):
    sport = SportSummarySerializer(read_only=True)
    positions = serializers.ListField(child=serializers.CharField(), read_only=True)

    class Meta:
        model = PlayerSport
        fields = ["id", "sport", "positions", "is_verified", "is_hidden"]
        read_only_fields = fields


class PlayerSportRatingSerializer(serializers.ModelSerializer):
    sport = SportSummarySerializer(read_only=True)

    class Meta:
        model = PlayerSportRating
        fields = [
            "id",
            "sport",
            "overall",
            "is_provisional",
            "matches_counted",
            "matches_played",
            "wins",
            "draws",
            "losses",
            "motm_awards",
            "last_match_at",
        ]
        read_only_fields = fields
