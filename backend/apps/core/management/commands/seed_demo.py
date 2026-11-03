"""Idempotent demo data.

Every phase extends this command with its own section (PLAN.md definition of done), so
a single `manage.py seed_demo` run always produces a complete, demo-able dataset.
Phase 00 seeded a platform admin; Phase 01 adds the sports catalogue and a handful of
onboarded demo players. Turfs, bookings and the rest arrive in later phases.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.players.services import complete_onboarding
from apps.sports.catalogue import sync_catalogue

#: Demo players, chosen to exercise the profile card: a multi-sport player, a keeper
#: whose excluded skill must not drag the overall down, and a cricketer.
DEMO_PLAYERS = [
    {
        "clerk_id": "seed_player_rafi",
        "first_name": "Rafi",
        "last_name": "Ahmed",
        "area": "Dhanmondi",
        "preferred_side": "right",
        "height_cm": 175,
        "weight_kg": "72.5",
        "bio": "Box-to-box midfielder. Evening slots only.",
        "attributes": {"stamina": 70, "agility": 62, "speed": 68, "strength": 55},
        "sports": [
            {
                "sport": "football",
                "positions": ["MID", "FWD"],
                "skills": {
                    "finishing": 62,
                    "passing": 71,
                    "dribbling": 65,
                    "defending": 54,
                    "positioning": 66,
                },
            },
            {
                "sport": "badminton",
                "positions": ["Doubles back"],
                "skills": {"smash": 60, "net_play": 52, "footwork": 58},
            },
        ],
    },
    {
        "clerk_id": "seed_player_shuvo",
        "first_name": "Shuvo",
        "last_name": "Rahman",
        "area": "Uttara",
        "preferred_side": "left",
        "height_cm": 186,
        "weight_kg": "80.0",
        "bio": "Keeper. Will play outfield if you are short.",
        "attributes": {"stamina": 55, "agility": 72, "speed": 50, "strength": 68},
        "sports": [
            {
                "sport": "football",
                "positions": ["GK"],
                "skills": {"goalkeeping": 73, "positioning": 64, "passing": 48},
            }
        ],
    },
    {
        "clerk_id": "seed_player_nabila",
        "first_name": "Nabila",
        "last_name": "Hossain",
        "area": "Banani",
        "preferred_side": "right",
        "height_cm": 164,
        "bio": "All-rounder, box cricket and futsal.",
        "attributes": {"stamina": 64, "agility": 70, "speed": 66, "strength": 48},
        "sports": [
            {
                "sport": "cricket",
                "positions": ["All-rounder"],
                "skills": {"batting": 66, "bowling": 61, "fielding": 70},
            },
            {
                "sport": "futsal",
                "positions": ["PIVOT"],
                "skills": {"finishing": 68, "close_control": 64, "passing": 60},
            },
        ],
    },
]


class Command(BaseCommand):
    help = "Create or refresh demo data for local development."

    def add_arguments(self, parser):
        parser.add_argument(
            "--admin-email",
            default="admin@turfapp.local",
            help="Email for the seeded platform admin.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        self.seed_platform_admin(options["admin_email"])
        self.seed_sports_catalogue()
        self.seed_demo_players()
        self.stdout.write(self.style.SUCCESS("Demo data seeded."))

    def seed_platform_admin(self, email: str) -> None:
        User = get_user_model()
        user, created = User.objects.update_or_create(
            clerk_id="seed_platform_admin",
            defaults={
                "email": email,
                "first_name": "Platform",
                "last_name": "Admin",
                "is_platform_admin": True,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        if created:
            # Local-only convenience: lets you reach /admin without a Clerk round-trip.
            user.set_password("admin")
            user.save(update_fields=["password"])
        verb = "Created" if created else "Updated"
        self.stdout.write(f"{verb} platform admin {user.email} (clerk_id={user.clerk_id})")

    def seed_sports_catalogue(self) -> None:
        """Re-sync the catalogue so edits to ``catalogue.py`` land without a migration."""
        counts = sync_catalogue()
        self.stdout.write(
            "Synced catalogue: " + ", ".join(f"{value} {name}" for name, value in counts.items())
        )

    def seed_demo_players(self) -> None:
        """Onboarded players, so the profile card has something to show immediately."""
        User = get_user_model()
        for spec in DEMO_PLAYERS:
            user, _ = User.objects.update_or_create(
                clerk_id=spec["clerk_id"],
                defaults={
                    "email": f"{spec['clerk_id']}@turfapp.local",
                    "first_name": spec["first_name"],
                    "last_name": spec["last_name"],
                },
            )
            data = {
                "display_name": f"{spec['first_name']} {spec['last_name']}",
                "area": spec["area"],
                "preferred_side": spec["preferred_side"],
                "height_cm": spec["height_cm"],
                "bio": spec["bio"],
                "attributes": spec["attributes"],
                "sports": spec["sports"],
            }
            if spec.get("weight_kg"):
                data["weight_kg"] = Decimal(spec["weight_kg"])

            profile = complete_onboarding(user=user, data=data)
            overalls = ", ".join(
                f"{rating.sport.name} {rating.overall}"
                for rating in profile.sport_ratings.select_related("sport")
            )
            self.stdout.write(f"Onboarded {profile.name} ({overalls})")
