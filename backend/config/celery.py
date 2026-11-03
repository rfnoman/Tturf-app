"""Celery application.

Periodic work in later phases: booking hold expiry and auto-confirm (Phase 03), join
request expiry (Phase 04), scorecard auto-confirm and MOTM vote close (Phase 05),
order cutoff and hydration reminders (Phase 09).
"""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("turfapp")
# Every CELERY_* setting in Django settings becomes a Celery setting.
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self) -> str:
    """Smoke test: `celery -A config call config.celery.debug_task`."""
    return f"ok: {self.request.id}"
