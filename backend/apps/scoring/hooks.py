"""The seam Phase 06's rating engine attaches to.

DOMAIN §8 says locking a scorecard triggers ratings, but ``apps.scoring`` must not import
``apps.ratings`` — the engine reads scorecards, so the dependency runs that way. Same
registry pattern as Phase 02's availability and Phase 04's match creation.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

logger = logging.getLogger(__name__)

ScorecardLockedHook = Callable[..., None]

_locked_hooks: list[ScorecardLockedHook] = []


def register_scorecard_locked_hook(hook: ScorecardLockedHook) -> None:
    """Called from an ``AppConfig.ready()``, which can run twice under the autoreloader."""
    if hook not in _locked_hooks:
        _locked_hooks.append(hook)


def clear_scorecard_locked_hooks() -> list[ScorecardLockedHook]:
    """Test hook: unsubscribe everything and hand back what was there.

    Returns the previous subscribers so a test that silences the registry can put it
    back — clearing it permanently would quietly disable the rating engine for every
    test that ran afterwards in the same process.
    """
    previous = list(_locked_hooks)
    _locked_hooks.clear()
    return previous


def restore_scorecard_locked_hooks(hooks) -> None:
    """Test hook: put back what `clear_scorecard_locked_hooks` returned."""
    _locked_hooks.clear()
    _locked_hooks.extend(hooks)


def scorecard_locked(*, scorecard, **context) -> None:
    """Fired once a scorecard becomes final.

    A subscriber that raises must not undo the lock — the scorecard is agreed, and a
    rating engine that cannot run is a problem to fix separately.
    """
    for hook in _locked_hooks:
        try:
            hook(scorecard=scorecard, **context)
        except Exception:
            logger.exception(
                "A scorecard_locked hook failed", extra={"scorecard": str(scorecard.id)}
            )
