"""Scheduled booking jobs (phase 03 step 2).

Two unattended transitions: releasing reservations nobody confirmed, and closing out
paid bookings whose slot has finished. Both are idempotent — the services re-check the
from-state — so a retry or an overlapping beat tick cannot double-apply anything.
"""

from __future__ import annotations

import logging

from celery import shared_task

from .services import complete_finished_bookings, expire_overdue_bookings

logger = logging.getLogger(__name__)


@shared_task(name="bookings.expire_overdue")
def expire_overdue() -> int:
    count = expire_overdue_bookings()
    if count:
        logger.info("Expired %s overdue reservation(s)", count)
    return count


@shared_task(name="bookings.complete_finished")
def complete_finished() -> int:
    count = complete_finished_bookings()
    if count:
        logger.info("Completed %s finished booking(s)", count)
    return count
