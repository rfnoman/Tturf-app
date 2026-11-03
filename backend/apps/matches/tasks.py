"""Scheduled match jobs (DOMAIN §6: requests and invites expire at match start)."""

from __future__ import annotations

import logging

from celery import shared_task

from .services import advance_match_statuses, expire_started_matches

logger = logging.getLogger(__name__)


@shared_task(name="matches.expire_pending")
def expire_pending() -> int:
    count = expire_started_matches()
    if count:
        logger.info("Expired %s pending request(s)/invite(s)", count)
    return count


@shared_task(name="matches.advance_statuses")
def advance_statuses() -> int:
    return advance_match_statuses()
