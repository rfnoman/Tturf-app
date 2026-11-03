"""Expose the Celery app so `celery -A config` and shared_task work."""

from .celery import app as celery_app

__all__ = ("celery_app",)
