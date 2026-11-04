"""Cache invalidation for the public turf page (Phase 11 step 3).

The page joins a turf with its grounds, opening hours, price rules, closures and
amenities, and a dozen endpoints can change one of those. Hooking the models rather
than the endpoints means a new endpoint cannot forget to invalidate — the only version
of this that stays correct.

Bumping a version key makes every cached turf unreachable at once rather than deleting
one. That is deliberate: the page is cached for two minutes, so the cost of dropping
all of them is one rebuild each, and the cost of trying to work out exactly which turfs
a price-rule change affects is a bug.
"""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.core.cache import invalidate

from .models import Amenity, Closure, Ground, OperatingHours, PriceRule, Turf


@receiver(post_save, sender=Turf)
@receiver(post_save, sender=Ground)
@receiver(post_save, sender=OperatingHours)
@receiver(post_save, sender=PriceRule)
@receiver(post_save, sender=Closure)
@receiver(post_save, sender=Amenity)
@receiver(post_delete, sender=Ground)
@receiver(post_delete, sender=OperatingHours)
@receiver(post_delete, sender=PriceRule)
@receiver(post_delete, sender=Closure)
def drop_cached_turfs(sender, **kwargs) -> None:
    invalidate("turfs")
