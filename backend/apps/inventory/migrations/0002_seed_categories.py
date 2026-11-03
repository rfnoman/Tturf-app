"""Seed the product categories so a fresh database can hold a product.

Only the categories: products belong to a turf or to the platform's buyer, and seeding
invented stock into a real deployment would be worse than an empty shelf. `seed_demo`
fills the shelves for development.
"""

from django.db import migrations

from apps.inventory.catalogue import sync_categories


def seed(apps, schema_editor):
    sync_categories(apps.get_model("inventory", "ProductCategory"))


def unseed(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
