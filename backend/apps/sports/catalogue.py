"""The seeded sports catalogue (DOMAIN §2 and §7).

The data lives here as plain dictionaries, and ``sync_catalogue`` upserts it. Two callers
share it:

* the data migration ``0002_seed_catalogue``, which passes the migration's historical
  model registry so a fresh database is usable immediately;
* ``manage.py seed_demo``, which passes nothing and gets the live models.

Keeping one definition means a catalogue change is a single edit, and re-running either
caller is idempotent — rows are matched on their natural keys (``slug`` / ``key``), never
recreated.

**The migration caller is the awkward one**, and `only_existing` below exists for it: a
data migration runs *today's* code against *that migration's* schema, so a column added
later simply is not there. Writing `label_bn` unconditionally broke every fresh database
while every existing one kept working — which is precisely the failure that only shows
up under `pytest --create-db` and on the first real deploy.

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
        "label_bn": "স্ট্যামিনা",
        "description": "How long you keep your level up over a full match.",
        "order": 1,
    },
    {
        "key": "agility",
        "label": "Agility",
        "label_bn": "ক্ষিপ্রতা",
        "description": "Changing direction and reacting in tight spaces.",
        "order": 2,
    },
    {
        "key": "speed",
        "label": "Speed",
        "label_bn": "গতি",
        "description": "Flat-out pace over short and long distances.",
        "order": 3,
    },
    {
        "key": "strength",
        "label": "Strength",
        "label_bn": "শক্তি",
        "description": "Holding your ground in a physical contest.",
        "order": 4,
    },
]

#: Every sport collects minutes played, which Phase 09 turns into calories.
MINUTES_PLAYED = {
    "key": "minutes_played",
    "label": "Minutes played",
    "label_bn": "খেলার মিনিট",
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
        "name_bn": "ফুটবল",
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
            {
                "key": "finishing",
                "label": "Finishing",
                "label_bn": "ফিনিশিং",
                "weight": "1.000",
                "order": 1,
            },
            {"key": "passing", "label": "Passing", "label_bn": "পাস", "weight": "1.000", "order": 2},
            {
                "key": "dribbling",
                "label": "Dribbling",
                "label_bn": "ড্রিবলিং",
                "weight": "0.900",
                "order": 3,
            },
            {
                "key": "defending",
                "label": "Defending",
                "label_bn": "ডিফেন্ডিং",
                "weight": "1.000",
                "order": 4,
            },
            {
                "key": "positioning",
                "label": "Positioning",
                "label_bn": "পজিশনিং",
                "weight": "0.800",
                "order": 5,
            },
            {
                "key": "goalkeeping",
                "label": "Goalkeeping",
                "label_bn": "গোলকিপিং",
                "weight": "1.000",
                "order": 6,
                # Only keepers rate this, so it must not drag an outfielder's overall down.
                "counts_toward_overall": False,
            },
        ],
        "positions": ["GK", "DEF", "MID", "FWD"],
        "stats": [
            {"key": "goals", "label": "Goals", "label_bn": "গোল", "max_value": 50, "order": 1},
            {
                "key": "assists",
                "label": "Assists",
                "label_bn": "অ্যাসিস্ট",
                "max_value": 50,
                "order": 2,
            },
            {"key": "saves", "label": "Saves", "label_bn": "সেভ", "max_value": 100, "order": 3},
            {
                "key": "clean_sheet",
                "label": "Clean sheet",
                "label_bn": "ক্লিন শিট",
                "value_type": "bool",
                "max_value": 1,
                "order": 4,
            },
            {
                "key": "yellow",
                "label": "Yellow cards",
                "label_bn": "হলুদ কার্ড",
                "max_value": 2,
                "is_positive": False,
                "order": 5,
            },
            {
                "key": "red",
                "label": "Red cards",
                "label_bn": "লাল কার্ড",
                "max_value": 1,
                "is_positive": False,
                "order": 6,
            },
        ],
    },
    {
        "slug": "futsal",
        "name": "Futsal",
        "name_bn": "ফুটসাল",
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
            {
                "key": "finishing",
                "label": "Finishing",
                "label_bn": "ফিনিশিং",
                "weight": "1.000",
                "order": 1,
            },
            {
                "key": "close_control",
                "label": "Close control",
                "label_bn": "বল নিয়ন্ত্রণ",
                "weight": "1.000",
                "order": 2,
            },
            {"key": "passing", "label": "Passing", "label_bn": "পাস", "weight": "0.900", "order": 3},
            {
                "key": "defending",
                "label": "Defending",
                "label_bn": "ডিফেন্ডিং",
                "weight": "0.900",
                "order": 4,
            },
            {
                "key": "goalkeeping",
                "label": "Goalkeeping",
                "label_bn": "গোলকিপিং",
                "weight": "1.000",
                "order": 5,
                "counts_toward_overall": False,
            },
        ],
        "positions": ["GK", "DEF", "WING", "PIVOT"],
        "stats": [
            {"key": "goals", "label": "Goals", "label_bn": "গোল", "max_value": 50, "order": 1},
            {
                "key": "assists",
                "label": "Assists",
                "label_bn": "অ্যাসিস্ট",
                "max_value": 50,
                "order": 2,
            },
            {"key": "saves", "label": "Saves", "label_bn": "সেভ", "max_value": 100, "order": 3},
            {
                "key": "yellow",
                "label": "Yellow cards",
                "label_bn": "হলুদ কার্ড",
                "max_value": 2,
                "is_positive": False,
                "order": 4,
            },
            {
                "key": "red",
                "label": "Red cards",
                "label_bn": "লাল কার্ড",
                "max_value": 1,
                "is_positive": False,
                "order": 5,
            },
        ],
    },
    {
        "slug": "cricket",
        "name": "Cricket",
        "name_bn": "ক্রিকেট",
        "icon": "🏏",
        "met_value": "4.80",
        "order": 3,
        "description": "Box cricket on a turf, or nets for batting and bowling practice.",
        "formats": [
            {
                "slug": "box",
                "name": "Box cricket",
                "name_bn": "বক্স ক্রিকেট",
                "players_per_side": 8,
                "order": 1,
            },
            {"slug": "nets", "name": "Nets", "name_bn": "নেট", "players_per_side": 4, "order": 2},
            {"slug": "t20", "name": "T20", "players_per_side": 11, "order": 3},
        ],
        "attribute_weights": {
            "stamina": "0.600",
            "agility": "0.800",
            "speed": "0.700",
            "strength": "0.900",
        },
        "skills": [
            {
                "key": "batting",
                "label": "Batting",
                "label_bn": "ব্যাটিং",
                "weight": "1.000",
                "order": 1,
            },
            {
                "key": "bowling",
                "label": "Bowling",
                "label_bn": "বোলিং",
                "weight": "1.000",
                "order": 2,
            },
            {
                "key": "fielding",
                "label": "Fielding",
                "label_bn": "ফিল্ডিং",
                "weight": "0.800",
                "order": 3,
            },
            {
                "key": "wicket_keeping",
                "label": "Wicket keeping",
                "label_bn": "উইকেটকিপিং",
                "weight": "1.000",
                "order": 4,
                "counts_toward_overall": False,
            },
        ],
        "positions": ["Batter", "Bowler", "All-rounder", "Wicket keeper"],
        "stats": [
            {"key": "runs", "label": "Runs", "label_bn": "রান", "max_value": 500, "order": 1},
            {
                "key": "balls",
                "label": "Balls faced",
                "label_bn": "খেলা বল",
                "max_value": 500,
                "order": 2,
            },
            {
                "key": "wickets",
                "label": "Wickets",
                "label_bn": "উইকেট",
                "max_value": 20,
                "order": 3,
            },
            {
                "key": "overs",
                "label": "Overs bowled",
                "label_bn": "ওভার",
                "value_type": "decimal",
                "max_value": 50,
                "order": 4,
            },
            {
                "key": "runs_conceded",
                "label": "Runs conceded",
                "label_bn": "দেওয়া রান",
                "max_value": 500,
                "is_positive": False,
                "order": 5,
            },
            {"key": "catches", "label": "Catches", "label_bn": "ক্যাচ", "max_value": 20, "order": 6},
        ],
    },
    {
        "slug": "badminton",
        "name": "Badminton",
        "name_bn": "ব্যাডমিন্টন",
        "icon": "🏸",
        "met_value": "5.50",
        "order": 4,
        "description": "Indoor singles or doubles on a marked court.",
        "formats": [
            {
                "slug": "singles",
                "name": "Singles",
                "name_bn": "সিঙ্গেলস",
                "players_per_side": 1,
                "order": 1,
            },
            {
                "slug": "doubles",
                "name": "Doubles",
                "name_bn": "ডাবলস",
                "players_per_side": 2,
                "order": 2,
            },
        ],
        "attribute_weights": {
            "stamina": "0.900",
            "agility": "1.000",
            "speed": "0.900",
            "strength": "0.500",
        },
        "skills": [
            {"key": "smash", "label": "Smash", "label_bn": "স্ম্যাশ", "weight": "1.000", "order": 1},
            {
                "key": "net_play",
                "label": "Net play",
                "label_bn": "নেট খেলা",
                "weight": "0.900",
                "order": 2,
            },
            {
                "key": "footwork",
                "label": "Footwork",
                "label_bn": "ফুটওয়ার্ক",
                "weight": "1.000",
                "order": 3,
            },
            {"key": "serve", "label": "Serve", "label_bn": "সার্ভ", "weight": "0.700", "order": 4},
            {
                "key": "defence",
                "label": "Defence",
                "label_bn": "ডিফেন্স",
                "weight": "0.900",
                "order": 5,
            },
        ],
        "positions": ["Singles", "Doubles front", "Doubles back"],
        "stats": [
            {
                "key": "sets_won",
                "label": "Sets won",
                "label_bn": "জেতা সেট",
                "max_value": 5,
                "order": 1,
            },
            {
                "key": "points_won",
                "label": "Points won",
                "label_bn": "জেতা পয়েন্ট",
                "max_value": 200,
                "order": 2,
            },
            {
                "key": "aces",
                "label": "Service aces",
                "label_bn": "সার্ভিস এস",
                "max_value": 100,
                "order": 3,
            },
            {
                "key": "errors",
                "label": "Unforced errors",
                "label_bn": "নিজের ভুল",
                "max_value": 200,
                "is_positive": False,
                "order": 4,
            },
        ],
    },
]


def only_existing(model, values: dict) -> dict:
    """Drop keys the given model does not have a field for.

    A historical model from a data migration has the columns that existed *at that
    migration*, not the ones that exist now. Filtering here means the catalogue can gain
    a column without breaking the migration that seeds it, and without the migration
    having to be rewritten every time (Phase 11 step 1 added the `_bn` columns; this is
    what makes that safe).
    """
    fields = {field.name for field in model._meta.get_fields()}
    return {key: value for key, value in values.items() if key in fields}


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
            defaults=only_existing(
                Attribute,
                {
                    "label": spec["label"],
                    "label_bn": spec.get("label_bn", ""),
                    "description": spec["description"],
                    "order": spec["order"],
                },
            ),
        )
        attributes[spec["key"]] = attribute
        counts["attributes"] += 1

    for spec in SPORTS:
        sport, _ = Sport.objects.update_or_create(
            slug=spec["slug"],
            defaults=only_existing(
                Sport,
                {
                    "name": spec["name"],
                    "name_bn": spec.get("name_bn", ""),
                    "icon": spec["icon"],
                    "description": spec["description"],
                    "met_value": Decimal(spec["met_value"]),
                    "positions": list(spec["positions"]),
                    "order": spec["order"],
                    "is_active": True,
                },
            ),
        )
        counts["sports"] += 1

        for fmt in spec["formats"]:
            SportFormat.objects.update_or_create(
                sport=sport,
                slug=fmt["slug"],
                defaults=only_existing(
                    SportFormat,
                    {
                        "name": fmt["name"],
                        "name_bn": fmt.get("name_bn", ""),
                        "players_per_side": fmt["players_per_side"],
                        "order": fmt["order"],
                        "is_active": True,
                    },
                ),
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
                defaults=only_existing(
                    Skill,
                    {
                        "label": skill["label"],
                        "label_bn": skill.get("label_bn", ""),
                        "weight": Decimal(skill["weight"]),
                        "counts_toward_overall": skill.get("counts_toward_overall", True),
                        "order": skill["order"],
                    },
                ),
            )
            counts["skills"] += 1

        for stat in [*spec["stats"], MINUTES_PLAYED]:
            StatDef.objects.update_or_create(
                sport=sport,
                key=stat["key"],
                defaults=only_existing(
                    StatDef,
                    {
                        "label": stat["label"],
                        "label_bn": stat.get("label_bn", ""),
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
                ),
            )
            counts["stats"] += 1

    return counts
