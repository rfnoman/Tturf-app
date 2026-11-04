"""Abstract model bases every domain model builds on.

All domain models exposed through the API use UUID primary keys (CLAUDE.md), so IDs
are safe to put in URLs and cannot be enumerated.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


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


class PlatformSetting(BaseModel):
    """A tunable business rule, overridable without a deploy (CLAUDE.md, Phase 11 step 5).

    Cutoff hours, commission percentages, rating caps — the numbers a business wants to
    move on a Tuesday afternoon. Every one of them already has a default in
    ``config/settings``; a row here *overrides* that default, and deleting the row
    restores it. That direction matters: the code is always runnable with no database
    behind it, and a typo in the admin is undone by deleting a row rather than by
    remembering what the number used to be.

    Values are stored as text and parsed on read, because the alternative — a column per
    type, or JSON — makes the admin form worse for the people who actually use it. The
    parse is forgiving in exactly one direction: an unparseable value falls back to the
    setting rather than raising, so a bad edit degrades to the old behaviour instead of
    taking the site down.
    """

    key = models.CharField(_("key"), max_length=100, unique=True)
    value = models.TextField(_("value"))
    description = models.CharField(_("what it does"), max_length=300, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="platform_settings_changed",
    )

    class Meta:
        verbose_name = _("platform setting")
        verbose_name_plural = _("platform settings")
        ordering = ["key"]

    def __str__(self) -> str:
        return f"{self.key} = {self.value}"
