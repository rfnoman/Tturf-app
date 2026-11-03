"""Shared pytest setup.

One job so far: keeping the migration-seeded reference tables alive around tests that
run with `django_db(transaction=True)`.

Those tests need real connections, so Django **truncates** every table between them
instead of rolling a transaction back — and truncation takes the sports catalogue, the
amenities and the product categories with it, leaving every later test in the run
looking at an empty catalogue. `serialized_rollback` would restore them, but only when
the test database was created in that run, and the project runs with `--reuse-db`.

Doing it here rather than in each module means the next transactional test anybody
writes inherits the fix instead of rediscovering it.
"""

from __future__ import annotations

import pytest


def reseed_reference_data() -> None:
    """Put back everything a data migration seeds."""
    from apps.inventory.catalogue import sync_categories
    from apps.inventory.models import ProductCategory
    from apps.sports.catalogue import sync_catalogue
    from apps.turfs.catalogue import sync_amenities

    sync_catalogue()
    sync_amenities()
    sync_categories(ProductCategory)


def _is_transactional(node) -> bool:
    marker = node.get_closest_marker("django_db")
    if marker is None:
        return False
    return bool(marker.kwargs.get("transaction") or marker.args[:1] == (True,))


@pytest.fixture(autouse=True)
def reference_data(request):
    """Seed what a transactional test needs, after its flush has already happened."""
    if _is_transactional(request.node):
        request.getfixturevalue("transactional_db")
        reseed_reference_data()
    yield


@pytest.fixture(scope="module", autouse=True)
def reference_data_after_module(django_db_setup, django_db_blocker):
    """Put the reference tables back for whatever runs next.

    Module-scoped on purpose: `transactional_db` flushes the database in its *own*
    teardown, which happens after any function-scoped fixture's. Restoring here means
    restoring after that flush, rather than being wiped by it.
    """
    yield
    with django_db_blocker.unblock():
        reseed_reference_data()
