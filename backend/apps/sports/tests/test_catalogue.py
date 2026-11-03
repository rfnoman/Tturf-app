"""The seeded catalogue and its re-sync."""

from __future__ import annotations

import pytest

from apps.sports.catalogue import ATTRIBUTES, SPORTS, sync_catalogue
from apps.sports.models import Attribute, Sport, SportSkill, StatDefinition

pytestmark = pytest.mark.django_db


def test_migration_seeded_every_sport():
    assert Sport.objects.count() == len(SPORTS)
    assert set(Sport.objects.values_list("slug", flat=True)) == {s["slug"] for s in SPORTS}


def test_shared_attributes_are_seeded_in_order():
    keys = list(Attribute.objects.values_list("key", flat=True))
    assert keys == [a["key"] for a in ATTRIBUTES]


def test_football_has_formats_skills_weights_and_stats():
    football = Sport.objects.get(slug="football")
    assert {f.slug for f in football.formats.all()} >= {"5v5", "7v7"}
    assert football.formats.get(slug="7v7").capacity == 14
    assert {s.key for s in football.skills.all()} >= {"finishing", "passing", "defending"}
    assert football.attribute_weights.count() == len(ATTRIBUTES)
    assert {s.key for s in football.stat_definitions.all()} >= {
        "goals",
        "assists",
        "saves",
        "clean_sheet",
        "yellow",
        "red",
        "minutes_played",
    }


def test_cricket_and_badminton_stats_match_domain():
    cricket = {s.key for s in Sport.objects.get(slug="cricket").stat_definitions.all()}
    assert cricket >= {"runs", "balls", "wickets", "overs", "runs_conceded", "catches"}
    badminton = {s.key for s in Sport.objects.get(slug="badminton").stat_definitions.all()}
    assert badminton >= {"sets_won", "points_won"}


def test_every_sport_records_minutes_played():
    for sport in Sport.objects.all():
        assert sport.stat_definitions.filter(key="minutes_played").exists()


def test_cards_are_marked_as_negative_stats():
    yellow = StatDefinition.objects.get(sport__slug="football", key="yellow")
    assert yellow.is_positive is False
    goals = StatDefinition.objects.get(sport__slug="football", key="goals")
    assert goals.is_positive is True


def test_goalkeeping_is_excluded_from_the_overall():
    """Only keepers rate it, so it must not drag an outfielder's overall down."""
    keeping = SportSkill.objects.get(sport__slug="football", key="goalkeeping")
    assert keeping.counts_toward_overall is False


def test_sync_is_idempotent():
    before = (
        Sport.objects.count(),
        SportSkill.objects.count(),
        StatDefinition.objects.count(),
        Attribute.objects.count(),
    )
    sync_catalogue()
    sync_catalogue()
    after = (
        Sport.objects.count(),
        SportSkill.objects.count(),
        StatDefinition.objects.count(),
        Attribute.objects.count(),
    )
    assert before == after


def test_sync_updates_edited_rows_in_place():
    football = Sport.objects.get(slug="football")
    football.met_value = 1
    football.save(update_fields=["met_value"])

    sync_catalogue()

    football.refresh_from_db()
    assert str(football.met_value) == "7.00"
    assert football.id == Sport.objects.get(slug="football").id
