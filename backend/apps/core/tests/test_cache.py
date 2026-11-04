"""The caching policy, as tests (Phase 11 step 3).

Two things have to hold or the cache is a liability rather than a saving: a change has
to be visible, and nothing per-player may be cached.
"""

from __future__ import annotations

import pytest
from django.core.cache import cache
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory
from apps.core.cache import cached, invalidate, version
from apps.turfs.tests.factories import ApprovedTurfFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clean_cache():
    cache.clear()
    yield
    cache.clear()


class TestVersionedCache:
    def test_builds_once_then_serves_the_cached_value(self):
        calls = []

        def build():
            calls.append(1)
            return {"answer": len(calls)}

        assert cached("demo", "k", 60, build) == {"answer": 1}
        assert cached("demo", "k", 60, build) == {"answer": 1}
        assert len(calls) == 1

    def test_invalidation_makes_every_key_in_the_namespace_unreachable(self):
        cached("demo", "a", 60, lambda: "first")
        cached("demo", "b", 60, lambda: "first")

        invalidate("demo")

        assert cached("demo", "a", 60, lambda: "second") == "second"
        assert cached("demo", "b", 60, lambda: "second") == "second"

    def test_a_namespace_nobody_has_written_is_version_one(self):
        assert version("never-used") == 1


class TestTurfPageCache:
    def test_an_edit_is_visible_immediately(self):
        # Two minutes of staleness is fine for an unrelated turf; it is not fine for the
        # owner who just renamed theirs and reloaded the page.
        turf = ApprovedTurfFactory(name="Before")
        client = APIClient()
        client.force_authenticate(UserFactory())

        assert client.get(f"/api/v1/turfs/{turf.slug}").data["name"] == "Before"

        turf.name = "After"
        turf.save()

        assert client.get(f"/api/v1/turfs/{turf.slug}").data["name"] == "After"

    def test_each_language_is_cached_separately(self):
        # The page carries sport names, which are translated (D63). One cache entry for
        # both languages would serve whichever reader arrived first.
        turf = ApprovedTurfFactory()
        client = APIClient()
        client.force_authenticate(UserFactory())

        english = client.get(f"/api/v1/turfs/{turf.slug}", HTTP_ACCEPT_LANGUAGE="en")
        bangla = client.get(f"/api/v1/turfs/{turf.slug}", HTTP_ACCEPT_LANGUAGE="bn")
        assert english.status_code == bangla.status_code == 200

    def test_the_cached_page_is_the_same_for_everybody(self):
        # This is what makes caching it safe at all. `TurfDetailSerializer` has no
        # reader-relative field — the owner's view (`my_role`, review feedback) is a
        # different serializer on a different route — and if that ever stops being true,
        # the cache would start serving one player the other's answer.
        turf = ApprovedTurfFactory()
        first, second = APIClient(), APIClient()
        first.force_authenticate(UserFactory())
        second.force_authenticate(UserFactory())

        assert (
            first.get(f"/api/v1/turfs/{turf.slug}").data
            == second.get(f"/api/v1/turfs/{turf.slug}").data
        )
