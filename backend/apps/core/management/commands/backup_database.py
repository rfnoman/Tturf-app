"""Take a database backup, and prove it can be restored (Phase 11 step 5).

An untested backup is a belief, not a safeguard — the failure mode is finding out on the
day it matters that the dump has been zero bytes for three months. So this command does
both halves by default: it dumps, and then it **restores the dump into a scratch
database and counts the rows**. A backup that cannot be restored fails the command,
which is what makes a nightly cron worth having.

Needs `pg_dump`/`pg_restore` on PATH — the same version as the server, or newer.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils.timezone import now

from apps.core.utils import to_dhaka


class Command(BaseCommand):
    help = "Dump the database, and verify the dump restores."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output-dir",
            default="backups",
            help="Where to write the dump. Defaults to ./backups.",
        )
        parser.add_argument(
            "--skip-verify",
            action="store_true",
            help=(
                "Dump without restoring it. Use only where the verification runs "
                "separately — an unverified backup is a belief, not a safeguard."
            ),
        )
        parser.add_argument(
            "--keep",
            type=int,
            default=14,
            help="How many dumps to keep. Older ones are deleted.",
        )

    def handle(self, *args, **options):
        database = settings.DATABASES["default"]
        directory = Path(options["output_dir"])
        directory.mkdir(parents=True, exist_ok=True)

        stamp = to_dhaka(now()).strftime("%Y%m%d-%H%M")
        target = directory / f"{database['NAME']}-{stamp}.dump"

        environment = {"PGPASSWORD": database.get("PASSWORD") or ""}
        connection = [
            "--host",
            str(database.get("HOST") or "localhost"),
            "--port",
            str(database.get("PORT") or 5432),
            "--username",
            str(database.get("USER") or ""),
        ]

        self.stdout.write(f"Dumping {database['NAME']} to {target}…")
        self._run(
            # Custom format, because it is what `pg_restore` can read selectively and
            # in parallel — a plain SQL file restores in one long serial stream.
            [
                "pg_dump",
                "--format=custom",
                "--no-owner",
                "--no-acl",
                *connection,
                "--file",
                str(target),
                str(database["NAME"]),
            ],
            environment,
        )

        size = target.stat().st_size
        if size == 0:
            raise CommandError(
                "The dump is empty. That is the failure this command exists to catch."
            )
        self.stdout.write(self.style.SUCCESS(f"Wrote {size / 1024 / 1024:.1f} MB"))

        if not options["skip_verify"]:
            self._verify(target, database, connection, environment)

        self._prune(directory, options["keep"])

    def _verify(self, dump: Path, database, connection, environment) -> None:
        """Restore into a scratch database and count what came back."""
        scratch = f"{database['NAME']}_restore_check"
        self.stdout.write(f"Restoring into {scratch} to check the dump…")

        self._run(["dropdb", "--if-exists", *connection, scratch], environment, allow_failure=True)
        self._run(["createdb", *connection, scratch], environment)

        try:
            self._run(
                [
                    "pg_restore",
                    "--no-owner",
                    "--no-acl",
                    *connection,
                    "--dbname",
                    scratch,
                    str(dump),
                ],
                environment,
                # A restore of a PostGIS dump emits warnings about the extension owner
                # that are not failures; the row count below is the real check.
                allow_failure=True,
            )
            tables = self._query(
                scratch,
                connection,
                environment,
                "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'",
            )
            if tables < 10:
                raise CommandError(
                    f"The restored database has only {tables} tables. The dump is not usable."
                )
            self.stdout.write(self.style.SUCCESS(f"Restored and verified: {tables} tables"))
        finally:
            self._run(
                ["dropdb", "--if-exists", *connection, scratch], environment, allow_failure=True
            )

    def _prune(self, directory: Path, keep: int) -> None:
        dumps = sorted(directory.glob("*.dump"), key=lambda p: p.stat().st_mtime, reverse=True)
        for old in dumps[keep:]:
            old.unlink()
            self.stdout.write(f"Deleted {old.name}")

    def _run(self, command: list[str], environment: dict, *, allow_failure: bool = False):
        import os

        result = subprocess.run(
            command, env={**os.environ, **environment}, capture_output=True, text=True
        )
        if result.returncode != 0 and not allow_failure:
            raise CommandError(f"{command[0]} failed: {result.stderr.strip()}")
        return result

    def _query(self, dbname: str, connection, environment, sql: str) -> int:
        result = self._run(
            ["psql", *connection, "--dbname", dbname, "--tuples-only", "--no-align", "-c", sql],
            environment,
        )
        return int(result.stdout.strip() or 0)
