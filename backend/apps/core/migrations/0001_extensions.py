"""Postgres extensions the whole project depends on.

The PostGIS backend creates the ``postgis`` extension itself in ``prepare_database()``,
but declaring it keeps the dependency explicit and ordered. ``btree_gist`` is **not**
created automatically and is required by the booking exclusion constraint in Phase 03
(``ground WITH =, time_range WITH &&``), so it is installed here once for every
environment and every freshly created test database.
"""

from django.contrib.postgres.operations import BtreeGistExtension, CreateExtension
from django.db import migrations


class Migration(migrations.Migration):
    initial = True

    operations = [
        CreateExtension("postgis"),
        BtreeGistExtension(),
    ]
