"""Scheduled scoring jobs (DOMAIN §7)."""

from __future__ import annotations

import logging

from celery import shared_task

from .services import auto_confirm_submitted_scorecards, close_finished_motm_voting

logger = logging.getLogger(__name__)


@shared_task(name="scoring.auto_confirm")
def auto_confirm() -> int:
    """No action within the window counts as agreement (DOMAIN §7)."""
    count = auto_confirm_submitted_scorecards()
    if count:
        logger.info("Auto-confirmed %s scorecard(s)", count)
    return count


@shared_task(name="scoring.close_motm")
def close_motm() -> int:
    count = close_finished_motm_voting()
    if count:
        logger.info("Closed MOTM voting on %s match(es)", count)
    return count
