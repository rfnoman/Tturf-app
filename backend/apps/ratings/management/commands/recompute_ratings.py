"""Replay rating history (DOMAIN §8: "so ratings can be recomputed from history")."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.players.models import PlayerProfile
from apps.ratings.services import recompute_all
from apps.sports.models import Sport


class Command(BaseCommand):
    help = "Recompute ratings from stored match history, for one player or everybody."

    def add_arguments(self, parser):
        parser.add_argument("--player", help="A player profile id; omit for everybody.")
        parser.add_argument("--sport", help="A sport slug; omit for every sport they play.")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )

    def handle(self, *args, **options):
        from django.db import transaction

        profiles = PlayerProfile.objects.all()
        if options["player"]:
            profiles = profiles.filter(id=options["player"])

        sports = Sport.objects.all()
        if options["sport"]:
            sports = sports.filter(slug=options["sport"])

        moved = 0
        checked = 0

        for profile in profiles.select_related("user"):
            for sport in sports:
                rating = profile.sport_ratings.filter(sport=sport).first()
                if rating is None:
                    continue
                checked += 1
                before = rating.overall

                # A dry run still has to do the work to know the answer, so it does it
                # inside a transaction it rolls back.
                if options["dry_run"]:
                    with transaction.atomic():
                        after = recompute_all(profile=profile, sport=sport).overall
                        transaction.set_rollback(True)
                else:
                    after = recompute_all(profile=profile, sport=sport).overall

                if after != before:
                    moved += 1
                    self.stdout.write(f"{profile.name} / {sport.name}: {before} → {after}")

        verb = "would change" if options["dry_run"] else "changed"
        self.stdout.write(self.style.SUCCESS(f"Checked {checked} ratings; {moved} {verb}."))
