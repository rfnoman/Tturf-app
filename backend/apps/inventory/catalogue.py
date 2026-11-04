"""Seed data for the product catalogue (DOMAIN §9).

Plain data, shared by the data migration and `seed_demo`, exactly as `apps.sports` does
it. Prices are realistic Dhaka counter prices in BDT.
"""

from __future__ import annotations

CATEGORIES = [
    {
        "slug": "drinks",
        "label": "Drinks",
        "label_bn": "পানীয়",
        "icon": "🥤",
        "order": 1,
        "is_consumable": True,
    },
    {
        "slug": "food",
        "label": "Food",
        "label_bn": "খাবার",
        "icon": "🍌",
        "order": 2,
        "is_consumable": True,
    },
    {
        "slug": "supplements",
        "label": "Supplements",
        "label_bn": "সাপ্লিমেন্ট",
        "icon": "💪",
        "order": 3,
        "is_consumable": True,
    },
    {
        "slug": "gear",
        "label": "Gear",
        "label_bn": "সরঞ্জাম",
        "icon": "⚽",
        "order": 4,
        "is_consumable": False,
    },
    {
        "slug": "apparel",
        "label": "Apparel",
        "label_bn": "পোশাক",
        "icon": "👕",
        "order": 5,
        "is_consumable": False,
    },
    {
        "slug": "accessories",
        "label": "Accessories",
        "label_bn": "আনুষঙ্গিক",
        "icon": "🧦",
        "order": 6,
        "is_consumable": False,
    },
    {
        "slug": "rental",
        "label": "Rental gear",
        "label_bn": "ভাড়ার সরঞ্জাম",
        "icon": "🎽",
        "order": 7,
        "is_consumable": False,
    },
]

#: The platform catalogue: what the Phase 08 store delivers.
PLATFORM_PRODUCTS = [
    {
        "slug": "mineral-water-500ml",
        "name": "Mineral water 500ml",
        "category": "drinks",
        "base_price": "20.00",
        "perishable": False,
        "tags": ["hydration"],
        "serving_size": "500 ml",
        "calories": 0,
    },
    {
        "slug": "electrolyte-drink-500ml",
        "name": "Electrolyte drink 500ml",
        "category": "drinks",
        "base_price": "60.00",
        "tags": ["hydration", "recovery"],
        "serving_size": "500 ml",
        "calories": 110,
        "carbs_g": "28.0",
        "sugar_g": "26.0",
    },
    {
        "slug": "glucose-sachet",
        "name": "Glucose sachet",
        "category": "supplements",
        "base_price": "15.00",
        "tags": ["hydration", "pre_match"],
        "serving_size": "25 g",
        "calories": 95,
        "carbs_g": "24.0",
        "sugar_g": "24.0",
    },
    {
        "slug": "protein-bar",
        "name": "Protein bar",
        "category": "supplements",
        "base_price": "220.00",
        "tags": ["protein", "recovery"],
        "serving_size": "60 g",
        "calories": 230,
        "protein_g": "20.0",
        "carbs_g": "22.0",
        "fat_g": "7.0",
        "sugar_g": "5.0",
    },
    {
        "slug": "whey-protein-1kg",
        "name": "Whey protein 1kg",
        "category": "supplements",
        "base_price": "4200.00",
        "tags": ["protein", "recovery"],
        "serving_size": "30 g",
        "calories": 120,
        "protein_g": "24.0",
        "carbs_g": "3.0",
        "fat_g": "1.5",
    },
    {
        "slug": "football-size-5",
        "name": "Football (size 5)",
        "category": "gear",
        "base_price": "1800.00",
        "tags": ["gear"],
        "sports": ["football"],
    },
    {
        "slug": "shin-guards",
        "name": "Shin guards",
        "category": "gear",
        "base_price": "650.00",
        "tags": ["gear"],
        "sports": ["football", "futsal"],
    },
    {
        "slug": "grip-socks",
        "name": "Grip socks",
        "category": "apparel",
        "base_price": "550.00",
        "tags": ["gear"],
        "sports": ["football", "futsal"],
    },
    {
        "slug": "shuttlecocks-tube",
        "name": "Shuttlecocks (tube of 6)",
        "category": "accessories",
        "base_price": "900.00",
        "tags": ["gear"],
        "sports": ["badminton"],
    },
]

#: What a turf keeps behind its own counter. Created for every seeded turf.
TURF_PRODUCTS = [
    {
        "slug": "mineral-water-500ml",
        "name": "Mineral water 500ml",
        "category": "drinks",
        "base_price": "25.00",
        "perishable": False,
        "tags": ["hydration"],
        "serving_size": "500 ml",
        "calories": 0,
        "on_hand": 48,
    },
    {
        "slug": "electrolyte-drink-500ml",
        "name": "Electrolyte drink 500ml",
        "category": "drinks",
        "base_price": "70.00",
        "tags": ["hydration", "recovery"],
        "serving_size": "500 ml",
        "calories": 110,
        "carbs_g": "28.0",
        "sugar_g": "26.0",
        "on_hand": 24,
    },
    {
        "slug": "banana",
        "name": "Banana",
        "category": "food",
        "base_price": "15.00",
        "perishable": True,
        "tags": ["pre_match", "vegan", "low_sugar"],
        "serving_size": "1 piece",
        "calories": 90,
        "carbs_g": "23.0",
        "sugar_g": "12.0",
        "on_hand": 30,
    },
    {
        "slug": "tea",
        "name": "Cha",
        "category": "drinks",
        "base_price": "20.00",
        "perishable": True,
        "tags": [],
        "serving_size": "1 cup",
        "calories": 60,
        "sugar_g": "8.0",
        "caffeine_mg": 30,
        "on_hand": 50,
    },
    {
        "slug": "bib-set",
        "name": "Training bibs (set of 10)",
        "category": "rental",
        "base_price": "0.00",
        "kind": "rental",
        "rental_price_per_match": "150.00",
        "deposit": "500.00",
        "tags": ["gear"],
        "sports": ["football", "futsal"],
        "on_hand": 4,
    },
    {
        "slug": "match-football",
        "name": "Match football",
        "category": "rental",
        "base_price": "0.00",
        "kind": "rental",
        "rental_price_per_match": "100.00",
        "deposit": "1000.00",
        "tags": ["gear"],
        "sports": ["football"],
        "on_hand": 6,
    },
]


def sync_categories(registry) -> dict:
    """Upsert the categories. ``registry`` is the model, so migrations can pass the
    historical one.

    Which is exactly why the defaults are filtered: a data migration runs *today's* code
    against *that migration's* schema, so a column added later simply is not there.
    Writing `label_bn` unconditionally broke every database built from migrations while
    every existing one kept working — the failure that only appears under
    `pytest --create-db` and on a first deploy.
    """
    from apps.sports.catalogue import only_existing

    categories = {}
    for row in CATEGORIES:
        category, _ = registry.objects.update_or_create(
            slug=row["slug"],
            defaults=only_existing(
                registry,
                {
                    "label": row["label"],
                    "label_bn": row.get("label_bn", ""),
                    "icon": row["icon"],
                    "order": row["order"],
                    "is_consumable": row["is_consumable"],
                },
            ),
        )
        categories[row["slug"]] = category
    return categories
