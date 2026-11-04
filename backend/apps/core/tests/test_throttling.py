"""The rate limits bite (Phase 11 step 4).

A throttle class that is configured but never reached is the worst of both worlds: it
reads as protection in review and is none in production. Each test here drives one past
its limit and asserts a 429.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.matches.tests.factories import make_match
from apps.players.services import complete_onboarding

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_throttle_history():
    # DRF keeps its counters in the cache, so one test's requests would otherwise count
    # against the next one's limit.
    cache.clear()
    yield
    cache.clear()


def onboard(user):
    return complete_onboarding(
        user=user,
        data={
            "attributes": {"stamina": 60, "agility": 60, "speed": 60, "strength": 60},
            "sports": [{"sport": "football", "positions": [], "skills": {"finishing": 60}}],
        },
    )


class TestReachingPeople:
    def test_a_burst_of_join_requests_is_refused(self, monkeypatch):
        # The rate is patched on the class rather than through `settings`: DRF reads
        # `DEFAULT_THROTTLE_RATES` through its own cached `api_settings`, so a settings
        # override only takes effect if nothing has read it yet — which makes the test
        # pass alone and fail in a full run.
        from apps.core.throttling import ReachingPeopleThrottle

        monkeypatch.setattr(ReachingPeopleThrottle, "get_rate", lambda self: "3/hour")

        player = UserFactory()
        onboard(player)
        client = APIClient()
        client.force_authenticate(player)

        codes = []
        for _ in range(5):
            match = make_match(booker=UserFactory())
            codes.append(client.post(f"/api/v1/matches/{match.id}/request", {}).status_code)

        assert 429 in codes, f"No request was throttled: {codes}"


class TestOrdinaryUseIsNotThrottled:
    def test_reading_the_board_repeatedly_is_fine(self):
        """The limits are a ceiling for a script, not a budget for a person.

        Somebody filtering the board interactively fires a request per change, and the
        day that starts returning 429 is the day the limits are wrong.
        """
        player = UserFactory()
        onboard(player)
        client = APIClient()
        client.force_authenticate(player)

        codes = {client.get("/api/v1/matches/board").status_code for _ in range(40)}

        assert codes == {200}
