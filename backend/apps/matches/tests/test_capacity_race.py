"""The last spot, contested for real (phase 04 step 5: "capacity race").

The phase brief asks for "two approvals for the last spot". A single-threaded test only
proves the second call sees the first one's write; it says nothing about what happens
when two organisers (or one organiser double-clicking) approve at the same instant.
That is what ``select_for_update`` in ``add_player`` is for, and the only way to exercise
it is real threads on real connections.
"""

from __future__ import annotations

import threading

import pytest
from django.core.exceptions import ValidationError
from django.db import connections

from apps.accounts.tests.factories import UserFactory
from apps.matches.models import JoinRequest, MatchPlayer
from apps.matches.services import add_player, decide_join_request, request_to_join

from .factories import make_match

pytestmark = pytest.mark.django_db(transaction=True)


def run_concurrently(targets):
    """Run callables on real threads, lined up so they genuinely collide."""
    results: list = []
    barrier = threading.Barrier(len(targets))

    def runner(fn):
        try:
            barrier.wait(timeout=15)
            results.append(fn())
        except Exception as exc:
            results.append(exc)
        finally:
            connections.close_all()

    threads = [threading.Thread(target=runner, args=(fn,)) for fn in targets]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
    return results


def test_two_simultaneous_approvals_cannot_both_take_the_last_spot():
    """Acceptance: the last spot can't be given twice."""
    booker = UserFactory()
    match = make_match(booker=booker, fmt="5v5", max_players=2)

    first, second = UserFactory(), UserFactory()
    request_one = request_to_join(match=match, user=first)
    request_two = request_to_join(match=match, user=second)

    results = run_concurrently(
        [
            lambda: decide_join_request(request=request_one, approver=booker, approve=True),
            lambda: decide_join_request(request=request_two, approver=booker, approve=True),
        ]
    )

    approvals = [r for r in results if isinstance(r, JoinRequest)]
    failures = [r for r in results if isinstance(r, Exception)]

    assert len(approvals) == 1, f"expected one approval, got {results}"
    assert len(failures) == 1
    assert isinstance(failures[0], ValidationError)
    assert match.players.count() == 2


def test_many_simultaneous_adds_never_exceed_capacity():
    """The lock, not luck: more contention must not overfill the roster."""
    booker = UserFactory()
    match = make_match(booker=booker, fmt="5v5", max_players=4)
    hopefuls = [UserFactory() for _ in range(8)]

    results = run_concurrently(
        [
            (lambda user=user: add_player(match=match, player=user, source="request"))
            for user in hopefuls
        ]
    )

    added = [r for r in results if isinstance(r, MatchPlayer)]
    # Capacity 4, with the booker already in it: exactly three more get in.
    assert len(added) == 3
    assert match.players.count() == 4
