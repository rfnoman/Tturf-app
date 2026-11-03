"""Seeded amenities (DOMAIN §4).

Same pattern as the sports catalogue: plain data plus one idempotent ``sync``, shared by
a data migration and ``seed_demo``, so a fresh database is usable and adding an amenity
later needs no migration.
"""

from __future__ import annotations

from typing import Any

AMENITIES: list[dict[str, Any]] = [
    {"key": "floodlights", "label": "Floodlights", "icon": "💡", "order": 1},
    {"key": "parking", "label": "Parking", "icon": "🅿️", "order": 2},
    {"key": "changing_room", "label": "Changing room", "icon": "🚪", "order": 3},
    {"key": "washroom", "label": "Washroom", "icon": "🚻", "order": 4},
    {"key": "cafe", "label": "Cafe", "icon": "☕", "order": 5},
    {"key": "drinking_water", "label": "Drinking water", "icon": "🚰", "order": 6},
    {"key": "first_aid", "label": "First aid", "icon": "🩹", "order": 7},
    {"key": "equipment_rental", "label": "Equipment rental", "icon": "⚽", "order": 8},
    {"key": "seating", "label": "Spectator seating", "icon": "🪑", "order": 9},
    {"key": "cctv", "label": "CCTV", "icon": "📹", "order": 10},
]


def sync_amenities(registry=None) -> int:
    if registry is None:
        from django.apps import apps as registry

    Amenity = registry.get_model("turfs", "Amenity")
    for spec in AMENITIES:
        Amenity.objects.update_or_create(
            key=spec["key"],
            defaults={"label": spec["label"], "icon": spec["icon"], "order": spec["order"]},
        )
    return len(AMENITIES)
