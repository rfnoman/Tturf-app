"""Every cell of the DOMAIN §9 fulfilment matrix, including the cutoff boundaries.

The matrix is the business rule this whole phase exists to express, so it is tested as a
matrix: each source × each option, with the reason a refusal gives checked as carefully
as the refusal itself. A shopper told "not available" with no reason cannot act on it.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.conf import settings
from django.test import override_settings

from apps.accounts.tests.factories import UserFactory
from apps.store.models import Fulfilment
from apps.store.services import (
    add_to_cart,
    cutoff_hours,
    fulfilment_options,
    option_for,
    zone_for,
)

from .factories import address_for, dhaka_zone, match_in, platform_product, turf_shelf

pytestmark = pytest.mark.django_db

CUTOFF = int(settings.TURF_DELIVERY_CUTOFF_HOURS)


def options_for(**kwargs):
    return {option.kind: option for option in fulfilment_options(**kwargs)}


class TestTurfStock:
    """DECISIONS D4: a turf's own stock is pickup only in v1."""

    def test_pickup_is_the_only_option(self):
        turf, _cashier, _product, item = turf_shelf()
        player = UserFactory()

        options = options_for(user=player, location=item.location)

        assert options[Fulfilment.PICKUP_AT_TURF].available is True
        assert options[Fulfilment.DELIVER_TO_TURF].available is False
        assert options[Fulfilment.DELIVER_TO_ADDRESS].available is False

    def test_every_refusal_explains_itself(self):
        turf, _cashier, _product, item = turf_shelf()
        options = fulfilment_options(user=UserFactory(), location=item.location)

        for option in options:
            if not option.available:
                assert option.reason, option.kind

    def test_delivery_to_an_address_is_refused_even_with_one_given(self):
        turf, _cashier, _product, item = turf_shelf()
        player = UserFactory()
        dhaka_zone()

        options = options_for(user=player, location=item.location, address=address_for(player))
        assert options[Fulfilment.DELIVER_TO_ADDRESS].available is False
        assert "pick it up" in options[Fulfilment.DELIVER_TO_ADDRESS].reason.lower()


class TestPlatformToAddress:
    def test_delivery_to_a_covered_area_carries_the_zone_fee(self):
        _product, item = platform_product()
        player = UserFactory()
        dhaka_zone(fee="60.00", eta=4)

        option = options_for(user=player, location=item.location, address=address_for(player))[
            Fulfilment.DELIVER_TO_ADDRESS
        ]

        assert option.available is True
        assert option.fee == Decimal("60.00")
        assert option.eta_hours == 4

    def test_an_area_nobody_covers_is_refused_politely(self):
        _product, item = platform_product()
        player = UserFactory()
        dhaka_zone(name="Dhanmondi")

        option = options_for(
            user=player,
            location=item.location,
            address=address_for(player, area="Savar"),
        )[Fulfilment.DELIVER_TO_ADDRESS]

        assert option.available is False
        assert "Savar" in option.reason

    def test_without_an_address_the_option_asks_for_one(self):
        _product, item = platform_product()
        option = options_for(user=UserFactory(), location=item.location)[
            Fulfilment.DELIVER_TO_ADDRESS
        ]

        assert option.available is False
        assert "address" in option.reason.lower()

    def test_an_inactive_zone_does_not_count(self):
        _product, item = platform_product()
        player = UserFactory()
        dhaka_zone(is_active=False)

        assert (
            options_for(user=player, location=item.location, address=address_for(player))[
                Fulfilment.DELIVER_TO_ADDRESS
            ].available
            is False
        )

    def test_the_cheapest_covering_zone_wins(self):
        dhaka_zone(name="Dhanmondi", fee="90.00")
        dhaka_zone(name="Dhanmondi", fee="60.00")

        zone = zone_for(area="Dhanmondi")
        assert zone.fee == Decimal("60.00")

    def test_there_is_nothing_to_pick_up_from_the_platform(self):
        _product, item = platform_product()
        option = options_for(user=UserFactory(), location=item.location)[Fulfilment.PICKUP_AT_TURF]
        assert option.available is False


class TestPlatformToTurf:
    """DECISIONS D5: only before the cutoff, and only for a match you are in."""

    def test_available_well_before_the_cutoff(self):
        _product, item = platform_product()
        player = UserFactory()
        match = match_in(CUTOFF + 6, player=player)

        option = options_for(user=player, location=item.location, match=match)[
            Fulfilment.DELIVER_TO_TURF
        ]
        assert option.available is True
        assert option.fee == Decimal("0")

    def test_refused_after_the_cutoff(self):
        _product, item = platform_product()
        player = UserFactory()
        match = match_in(CUTOFF - 1, player=player)

        option = options_for(user=player, location=item.location, match=match)[
            Fulfilment.DELIVER_TO_TURF
        ]
        assert option.available is False
        assert str(CUTOFF) in option.reason

    def test_a_minute_inside_the_cutoff_still_works(self):
        """The acceptance line: at 4:59 it works, at 5:01 it does not."""
        _product, item = platform_product()
        player = UserFactory()
        match = match_in(CUTOFF + (1 / 60), player=player)

        assert (
            options_for(user=player, location=item.location, match=match)[
                Fulfilment.DELIVER_TO_TURF
            ].available
            is True
        )

    def test_a_minute_past_the_cutoff_does_not(self):
        _product, item = platform_product()
        player = UserFactory()
        match = match_in(CUTOFF - (1 / 60), player=player)

        assert (
            options_for(user=player, location=item.location, match=match)[
                Fulfilment.DELIVER_TO_TURF
            ].available
            is False
        )

    def test_somebody_elses_match_is_refused(self):
        _product, item = platform_product()
        match = match_in(CUTOFF + 6)

        option = options_for(user=UserFactory(), location=item.location, match=match)[
            Fulfilment.DELIVER_TO_TURF
        ]
        assert option.available is False
        assert "not playing" in option.reason

    def test_without_a_match_the_option_asks_for_one(self):
        _product, item = platform_product()
        option = options_for(user=UserFactory(), location=item.location)[Fulfilment.DELIVER_TO_TURF]
        assert option.available is False
        assert "match" in option.reason.lower()

    @override_settings(TURF_DELIVERY_CUTOFF_HOURS=2)
    def test_the_cutoff_is_configurable(self):
        _product, item = platform_product()
        player = UserFactory()
        match = match_in(3, player=player)

        assert (
            options_for(user=player, location=item.location, match=match)[
                Fulfilment.DELIVER_TO_TURF
            ].available
            is True
        )

    def test_a_zone_may_override_the_cutoff(self):
        zone = dhaka_zone(turf_delivery_cutoff_hours=2)
        assert cutoff_hours(zone) == 2
        assert cutoff_hours(None) == CUTOFF

    def test_a_perishable_cannot_be_sent_to_a_turf(self):
        product, item = platform_product(name="Fresh juice", category="food", perishable=True)
        player = UserFactory()
        match = match_in(CUTOFF + 6, player=player)
        line = add_to_cart(user=player, stock_item=item)

        option = option_for(
            fulfilment_options(user=player, location=item.location, items=[line], match=match),
            Fulfilment.DELIVER_TO_TURF,
        )
        assert option.available is False
        assert "Fresh" in option.reason


def test_the_matrix_covers_every_cell():
    """Three options for each of the two sources, every time, available or not."""
    kinds = {Fulfilment.PICKUP_AT_TURF, Fulfilment.DELIVER_TO_TURF, Fulfilment.DELIVER_TO_ADDRESS}
    _product, warehouse_item = platform_product()
    _turf, _cashier, _turf_product, turf_item = turf_shelf()
    player = UserFactory()

    for location in (warehouse_item.location, turf_item.location):
        options = fulfilment_options(user=player, location=location)
        assert {option.kind for option in options} == kinds
