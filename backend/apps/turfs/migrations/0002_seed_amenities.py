"""Seed the amenity list so turf registration has something to offer."""

from django.db import migrations

from apps.turfs.catalogue import sync_amenities


def seed(apps, schema_editor):
    sync_amenities(apps)


def unseed(apps, schema_editor):
    # Deliberately a no-op: unapplying must not strip amenities off live turfs.
    pass


class Migration(migrations.Migration):
    dependencies = [("turfs", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
