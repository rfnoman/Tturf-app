"""Seed the sports catalogue so a fresh database is immediately usable.

The data itself lives in ``apps/sports/catalogue.py`` and is shared with
``manage.py seed_demo``; this migration only hands it the historical model registry.
The reverse is a no-op on purpose — unapplying a migration should not delete a sport
that player profiles and scorecards point at.
"""

from django.db import migrations

from apps.sports.catalogue import sync_catalogue


def seed(apps, schema_editor):
    sync_catalogue(apps)


def unseed(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("sports", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
