"""These tests are about what the hook does, so the hook has to be attached.

`RatingsConfig.ready()` registers it at startup, but other apps' tests clear the
registry to score cards in isolation. Re-registering here (it is idempotent) means a
ratings test passes or fails on its own merits, whatever ran before it.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def rating_hook_registered():
    from apps.ratings.hooks import on_scorecard_locked
    from apps.scoring.hooks import register_scorecard_locked_hook

    register_scorecard_locked_hook(on_scorecard_locked)
