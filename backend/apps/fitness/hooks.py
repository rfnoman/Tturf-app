"""What a locked scorecard means for the fitness layer."""

from __future__ import annotations


def on_scorecard_locked(*, scorecard, **_context) -> None:
    from .services import log_match_activity

    log_match_activity(scorecard=scorecard)
