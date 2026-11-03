"""What happens when a scorecard locks."""

from __future__ import annotations


def on_scorecard_locked(*, scorecard, **_context) -> None:
    from .services import apply_locked_scorecard

    apply_locked_scorecard(scorecard=scorecard)
