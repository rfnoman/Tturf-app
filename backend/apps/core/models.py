"""Abstract model bases every domain model builds on.

All domain models exposed through the API use UUID primary keys (CLAUDE.md), so IDs
are safe to put in URLs and cannot be enumerated.
"""

from __future__ import annotations

import uuid

from django.db import models


class UUIDModel(models.Model):
    """Primary key is a non-sequential UUID4."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(models.Model):
    """Adds creation/modification bookkeeping."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class BaseModel(UUIDModel, TimeStampedModel):
    """The usual starting point: UUID pk + timestamps."""

    class Meta:
        abstract = True
