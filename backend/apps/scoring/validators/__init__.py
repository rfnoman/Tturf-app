"""Per-sport scorecard validation (DOMAIN §7).

A scorecard is only worth computing ratings from if its numbers hang together, and what
"hang together" means is sport-specific: football goals must not exceed the team score,
cricket runs must reconcile with the total. So validation is a **registry keyed by sport
slug**, with a generic fallback.

That matters for more than tidiness. Sports are admin-curated and owners can propose new
ones (DOMAIN §2), so a sport will exist that this codebase has never heard of. It gets
the generic validator — min/max bounds and roster membership — rather than crashing or,
worse, silently accepting nonsense.

Register one with ``@register("slug")``; import it below so it is loaded at app ready.
"""

from __future__ import annotations

from collections.abc import Callable

#: Importing for the side effect of registering. Order does not matter.
from . import cricket, football, racket  # noqa: F401
from .base import (
    ScorecardData,
    ValidationIssue,
    generic_validator,
    register,
    validate_scorecard,
)

__all__ = [
    "Callable",
    "ScorecardData",
    "ValidationIssue",
    "generic_validator",
    "register",
    "validate_scorecard",
]
