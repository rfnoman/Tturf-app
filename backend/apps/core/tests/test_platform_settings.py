"""Database-backed business rules (Phase 11 step 5).

CLAUDE.md has said since Phase 00 that configurable rules live in one place and that
`setting()` would be the only thing that learned about the database. These pin both
halves: an override works, and a bad one cannot take the site down.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.core.cache import cache

from apps.core.models import PlatformSetting
from apps.core.utils import setting

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_setting_cache():
    cache.clear()
    yield
    cache.clear()


def test_falls_back_to_the_code_when_there_is_no_row(settings):
    settings.BOOKING_HORIZON_DAYS = 30

    assert setting("BOOKING_HORIZON_DAYS") == 30


def test_a_row_overrides_the_code(settings):
    settings.BOOKING_HORIZON_DAYS = 30
    PlatformSetting.objects.create(key="BOOKING_HORIZON_DAYS", value="45")

    assert setting("BOOKING_HORIZON_DAYS") == 45


def test_the_value_comes_back_as_the_type_the_code_uses(settings):
    # Stored as text, because a column per type makes the admin form worse for the
    # people who use it. Read back as whatever the default is.
    settings.A_NUMBER = 7
    settings.A_DECIMAL = Decimal("10.00")
    settings.A_FLAG = False
    PlatformSetting.objects.bulk_create(
        [
            PlatformSetting(key="A_NUMBER", value="12"),
            PlatformSetting(key="A_DECIMAL", value="12.50"),
            PlatformSetting(key="A_FLAG", value="yes"),
        ]
    )

    assert setting("A_NUMBER") == 12
    assert setting("A_DECIMAL") == Decimal("12.50")
    assert setting("A_FLAG") is True


def test_a_typo_degrades_to_yesterdays_behaviour(settings):
    """The one thing that must not happen is a bad edit taking the site down."""
    settings.BOOKING_HORIZON_DAYS = 30
    PlatformSetting.objects.create(key="BOOKING_HORIZON_DAYS", value="thirty")

    assert setting("BOOKING_HORIZON_DAYS") == 30


def test_deleting_the_row_restores_the_default(settings):
    settings.BOOKING_HORIZON_DAYS = 30
    row = PlatformSetting.objects.create(key="BOOKING_HORIZON_DAYS", value="45")
    assert setting("BOOKING_HORIZON_DAYS") == 45

    cache.clear()
    row.delete()

    assert setting("BOOKING_HORIZON_DAYS") == 30
