"""Idempotent demo data.

Every phase extends this command with its own section (PLAN.md definition of done), so
a single `manage.py seed_demo` run always produces a complete, demo-able dataset.
Phase 00 seeds only a platform admin; sports, turfs, bookings and so on arrive later.
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction


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
