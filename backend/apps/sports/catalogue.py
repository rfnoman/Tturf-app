"""The seeded sports catalogue (DOMAIN §2 and §7).

The data lives here as plain dictionaries, and ``sync_catalogue`` upserts it. Two callers
share it:

* the data migration ``0002_seed_catalogue``, which passes the migration's historical
  model registry so a fresh database is usable immediately;
* ``manage.py seed_demo``, which passes nothing and gets the live models.

Keeping one definition means a catalogue change is a single edit, and re-running either
caller is idempotent — rows are matched on their natural keys (``slug`` / ``key``), never
recreated.

MET values follow the 2024 Compendium of Physical Activities (soccer casual 7.0 /
competitive 10.0, indoor futsal 8.0, cricket 4.8, badminton social 5.5).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

#: Shared physical attributes. They belong to the player, not the sport (DOMAIN §3).
ATTRIBUTES: list[dict[str, Any]] = [
    {
        "key": "stamina",
        "label": "Stamina",
        "description": "How long you keep your level up over a full match.",
        "order": 1,
    },
    {
        "key": "agility",
        "label": "Agility",
        "description": "Changing direction and reacting in tight spaces.",
        "order": 2,
    },
    {
        "key": "speed",
        "label": "Speed",
        "description": "Flat-out pace over short and long distances.",
        "order": 3,
    },
    {
        "key": "strength",
        "label": "Strength",
        "description": "Holding your ground in a physical contest.",
        "order": 4,
    },
]

#: Every sport collects minutes played, which Phase 09 turns into calories.
MINUTES_PLAYED = {
    "key": "minutes_played",
    "label": "Minutes played",
    "value_type": "int",
    "scope": "player",
    "min_value": 0,
    "max_value": 240,
    "unit": "min",
    "is_positive": True,
    "show_on_profile": False,
    "order": 90,
}

SPORTS: list[dict[str, Any]] = [
    {
        "slug": "football",
        "name": "Football",
        "icon": "⚽",
        "met_value": "7.00",
        "order": 1,
        "description": "The default game on a Dhaka turf, usually 5v5 or 7v7 under lights.",
        "formats": [
            {"slug": "5v5", "name": "5v5", "players_per_side": 5, "order": 1},
            {"slug": "7v7", "name": "7v7", "players_per_side": 7, "order": 2},
            {"slug": "9v9", "name": "9v9", "players_per_side": 9, "order": 3},
            {"slug": "11v11", "name": "11v11", "players_per_side": 11, "order": 4},
        ],
        "attribute_weights": {
            "stamina": "1.000",
            "agility": "0.900",
            "speed": "1.000",
            "strength": "0.700",
        },
        "skills": [
            {"key": "finishing", "label": "Finishing", "weight": "1.000", "order": 1},
            {"key": "passing", "label": "Passing", "weight": "1.000", "order": 2},
            {"key": "dribbling", "label": "Dribbling", "weight": "0.900", "order": 3},
            {"key": "defending", "label": "Defending", "weight": "1.000", "order": 4},
            {"key": "positioning", "label": "Positioning", "weight": "0.800", "order": 5},
            {
                "key": "goalkeeping",
                "label": "Goalkeeping",
                "weight": "1.000",
                "order": 6,
                # Only keepers rate this, so it must not drag an outfielder's overall down.
                "counts_toward_overall": False,
            },
        ],
        "positions": ["GK", "DEF", "MID", "FWD"],
        "stats": [
            {"key": "goals", "label": "Goals", "max_value": 50, "order": 1},
            {"key": "assists", "label": "Assists", "max_value": 50, "order": 2},
            {"key": "saves", "label": "Saves", "max_value": 100, "order": 3},
            {
                "key": "clean_sheet",
                "label": "Clean sheet",
                "value_type": "bool",
                "max_value": 1,
                "order": 4,
            },
            {
                "key": "yellow",
                "label": "Yellow cards",
                "max_value": 2,
                "is_positive": False,
                "order": 5,
            },
            {
                "key": "red",
                "label": "Red cards",
                "max_value": 1,
                "is_positive": False,
                "order": 6,
            },
        ],
    },
    {
        "slug": "futsal",
        "name": "Futsal",
        "icon": "🥅",
        "met_value": "8.00",
        "order": 2,
        "description": "Indoor five-a-side on a hard court with a low-bounce ball.",
        "formats": [
            {"slug": "5v5", "name": "5v5", "players_per_side": 5, "order": 1},
            {"slug": "4v4", "name": "4v4", "players_per_side": 4, "order": 2},
        ],
        "attribute_weights": {
            "stamina": "0.900",
            "agility": "1.000",
            "speed": "0.900",
            "strength": "0.600",
        },
        "skills": [
            {"key": "finishing", "label": "Finishing", "weight": "1.000", "order": 1},
            {"key": "close_control", "label": "Close control", "weight": "1.000", "order": 2},
            {"key": "passing", "label": "Passing", "weight": "0.900", "order": 3},
            {"key": "defending", "label": "Defending", "weight": "0.900", "order": 4},
            {
                "key": "goalkeeping",
                "label": "Goalkeeping",
                "weight": "1.000",
                "order": 5,
                "counts_toward_overall": False,
            },
        ],
        "positions": ["GK", "DEF", "WING", "PIVOT"],
        "stats": [
            {"key": "goals", "label": "Goals", "max_value": 50, "order": 1},
            {"key": "assists", "label": "Assists", "max_value": 50, "order": 2},
            {"key": "saves", "label": "Saves", "max_value": 100, "order": 3},
            {
                "key": "yellow",
                "label": "Yellow cards",
                "max_value": 2,
                "is_positive": False,
                "order": 4,
            },
            {
                "key": "red",
                "label": "Red cards",
                "max_value": 1,
                "is_positive": False,
                "order": 5,
            },
        ],
    },
    {
        "slug": "cricket",
        "name": "Cricket",
        "icon": "🏏",
        "met_value": "4.80",
        "order": 3,
        "description": "Box cricket on a turf, or nets for batting and bowling practice.",
        "formats": [
            {"slug": "box", "name": "Box cricket", "players_per_side": 8, "order": 1},
            {"slug": "nets", "name": "Nets", "players_per_side": 4, "order": 2},
            {"slug": "t20", "name": "T20", "players_per_side": 11, "order": 3},
        ],
        "attribute_weights": {
            "stamina": "0.600",
            "agility": "0.800",
            "speed": "0.700",
            "strength": "0.900",
        },
        "skills": [
            {"key": "batting", "label": "Batting", "weight": "1.000", "order": 1},
            {"key": "bowling", "label": "Bowling", "weight": "1.000", "order": 2},
            {"key": "fielding", "label": "Fielding", "weight": "0.800", "order": 3},
            {
                "key": "wicket_keeping",
                "label": "Wicket keeping",
                "weight": "1.000",
                "order": 4,
                "counts_toward_overall": False,
            },
        ],
        "positions": ["Batter", "Bowler", "All-rounder", "Wicket keeper"],
        "stats": [
            {"key": "runs", "label": "Runs", "max_value": 500, "order": 1},
            {"key": "balls", "label": "Balls faced", "max_value": 500, "order": 2},
            {"key": "wickets", "label": "Wickets", "max_value": 20, "order": 3},
            {
                "key": "overs",
                "label": "Overs bowled",
                "value_type": "decimal",
                "max_value": 50,
                "order": 4,
            },
            {
                "key": "runs_conceded",
                "label": "Runs conceded",
                "max_value": 500,
                "is_positive": False,
                "order": 5,
            },
            {"key": "catches", "label": "Catches", "max_value": 20, "order": 6},
        ],
    },
    {
        "slug": "badminton",
        "name": "Badminton",
        "icon": "🏸",
        "met_value": "5.50",
        "order": 4,
        "description": "Indoor singles or doubles on a marked court.",
        "formats": [
            {"slug": "singles", "name": "Singles", "players_per_side": 1, "order": 1},
            {"slug": "doubles", "name": "Doubles", "players_per_side": 2, "order": 2},
        ],
        "attribute_weights": {
            "stamina": "0.900",
            "agility": "1.000",
            "speed": "0.900",
            "strength": "0.500",
        },
        "skills": [
            {"key": "smash", "label": "Smash", "weight": "1.000", "order": 1},
            {"key": "net_play", "label": "Net play", "weight": "0.900", "order": 2},
            {"key": "footwork", "label": "Footwork", "weight": "1.000", "order": 3},
            {"key": "serve", "label": "Serve", "weight": "0.700", "order": 4},
            {"key": "defence", "label": "Defence", "weight": "0.900", "order": 5},
        ],
        "positions": ["Singles", "Doubles front", "Doubles back"],
        "stats": [
            {"key": "sets_won", "label": "Sets won", "max_value": 5, "order": 1},
            {"key": "points_won", "label": "Points won", "max_value": 200, "order": 2},
            {"key": "aces", "label": "Service aces", "max_value": 100, "order": 3},
            {
                "key": "errors",
                "label": "Unforced errors",
                "max_value": 200,
                "is_positive": False,
                "order": 4,
            },
        ],
    },
]


def _models(registry):
    """Resolve the models from either the live registry or a migration's historical one."""
    if registry is None:
        from django.apps import apps as registry
    return (
        registry.get_model("sports", "Attribute"),
        registry.get_model("sports", "Sport"),
        registry.get_model("sports", "SportFormat"),
        registry.get_model("sports", "SportAttributeWeight"),
        registry.get_model("sports", "SportSkill"),
        registry.get_model("sports", "StatDefinition"),
    )


def sync_catalogue(registry=None) -> dict[str, int]:
    """Upsert attributes, sports, formats, weights, skills and stat definitions.

    Idempotent, and safe to re-run after the catalogue is edited: existing rows are
    updated in place so references from player profiles and scorecards survive.
    Rows removed from this file are left alone — deleting a sport that has history
    is an admin decision, not a migration's.
    """
    Attribute, Sport, SportFormat, Weight, Skill, StatDef = _models(registry)
    counts = dict.fromkeys(("attributes", "sports", "formats", "weights", "skills", "stats"), 0)

    attributes = {}
    for spec in ATTRIBUTES:
        attribute, _ = Attribute.objects.update_or_create(
            key=spec["key"],
            defaults={
                "label": spec["label"],
                "description": spec["description"],
                "order": spec["order"],
            },
        )
        attributes[spec["key"]] = attribute
        counts["attributes"] += 1

    for spec in SPORTS:
        sport, _ = Sport.objects.update_or_create(
            slug=spec["slug"],
            defaults={
                "name": spec["name"],
                "icon": spec["icon"],
                "description": spec["description"],
                "met_value": Decimal(spec["met_value"]),
                "positions": list(spec["positions"]),
                "order": spec["order"],
                "is_active": True,
            },
        )
        counts["sports"] += 1

        for fmt in spec["formats"]:
            SportFormat.objects.update_or_create(
                sport=sport,
                slug=fmt["slug"],
                defaults={
                    "name": fmt["name"],
                    "players_per_side": fmt["players_per_side"],
                    "order": fmt["order"],
                    "is_active": True,
                },
            )
            counts["formats"] += 1

        for key, weight in spec["attribute_weights"].items():
            Weight.objects.update_or_create(
                sport=sport,
                attribute=attributes[key],
                defaults={"weight": Decimal(weight)},
            )
            counts["weights"] += 1

        for skill in spec["skills"]:
            Skill.objects.update_or_create(
                sport=sport,
                key=skill["key"],
                defaults={
                    "label": skill["label"],
                    "weight": Decimal(skill["weight"]),
                    "counts_toward_overall": skill.get("counts_toward_overall", True),
                    "order": skill["order"],
                },
            )
            counts["skills"] += 1

        for stat in [*spec["stats"], MINUTES_PLAYED]:
            StatDef.objects.update_or_create(
                sport=sport,
                key=stat["key"],
                defaults={
                    "label": stat["label"],
                    "value_type": stat.get("value_type", "int"),
                    "scope": stat.get("scope", "player"),
                    "min_value": Decimal(str(stat.get("min_value", 0))),
                    "max_value": Decimal(str(stat["max_value"]))
                    if stat.get("max_value") is not None
                    else None,
                    "unit": stat.get("unit", ""),
                    "is_positive": stat.get("is_positive", True),
                    "show_on_profile": stat.get("show_on_profile", True),
                    "order": stat["order"],
                },
            )
            counts["stats"] += 1

    return counts
