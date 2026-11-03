"""Idempotent demo data.

Every phase extends this command with its own section (PLAN.md definition of done), so
a single `manage.py seed_demo` run always produces a complete, demo-able dataset.
Phase 00 seeded a platform admin; Phase 01 added the sports catalogue and onboarded demo
players; Phase 02 added five approved Dhaka turfs; Phase 03 adds bookings across the
state machine so every screen has something to show.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.players.services import complete_onboarding
from apps.sports.catalogue import sync_catalogue
from apps.sports.models import SportFormat
from apps.turfs.catalogue import sync_amenities
from apps.turfs.demo import DEMO_TURFS, price_decimal
from apps.turfs.models import Amenity, OperatingHours, PriceRule, Turf, TurfMembership
from apps.turfs.services import activate_ground, approve_turf, create_ground, create_turf

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
        self.seed_turfs()
        self.seed_bookings()
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

    def seed_turfs(self) -> None:
        """Five approved turfs across Dhaka, each fully priced and bookable.

        Built through the real services rather than bulk inserts, so the seed exercises
        the same validation an owner would hit — in particular `activate_ground`, which
        refuses a ground whose open hours are not fully priced. A broken demo price
        table therefore fails the seed instead of producing turfs with unbookable slots.
        """
        from django.contrib.gis.geos import Point

        User = get_user_model()
        admin = User.objects.get(clerk_id="seed_platform_admin")
        sync_amenities()
        amenities = {amenity.key: amenity for amenity in Amenity.objects.all()}
        formats = {
            (fmt.sport.slug, fmt.slug): fmt for fmt in SportFormat.objects.select_related("sport")
        }

        for spec in DEMO_TURFS:
            owner, _ = User.objects.update_or_create(
                clerk_id=f"seed_owner_{spec['slug']}",
                defaults={
                    "email": f"owner.{spec['slug']}@turfapp.local",
                    "first_name": spec["name"].split()[0],
                    "last_name": "Owner",
                },
            )

            turf = Turf.objects.filter(slug=spec["slug"]).first()
            if turf is None:
                turf = create_turf(
                    owner=owner,
                    name=spec["name"],
                    description=spec["description"],
                    address=spec["address"],
                    area=spec["area"],
                    phone=spec["phone"],
                    location=Point(spec["longitude"], spec["latitude"], srid=4326),
                )
                # create_turf picks a collision-free slug; pin it so re-runs match.
                turf.slug = spec["slug"]
                turf.save(update_fields=["slug"])
            turf.amenities.set([amenities[key] for key in spec["amenities"]])

            for weekday, opens, closes in spec["hours"]:
                OperatingHours.objects.update_or_create(
                    turf=turf,
                    weekday=weekday,
                    open_time=opens,
                    defaults={"close_time": closes},
                )

            for ground_spec in spec["grounds"]:
                ground = turf.grounds.filter(name=ground_spec["name"]).first()
                if ground is None:
                    ground = create_ground(
                        turf=turf,
                        name=ground_spec["name"],
                        surface=ground_spec["surface"],
                        max_players=ground_spec["max_players"],
                        slot_minutes=ground_spec["slot_minutes"],
                    )
                ground.sport_formats.set(
                    [formats[key] for key in ground_spec["formats"] if key in formats]
                )

                for weekdays, start, end, price, label in ground_spec["prices"]:
                    PriceRule.objects.update_or_create(
                        ground=ground,
                        weekdays=weekdays,
                        start_time=start,
                        defaults={
                            "end_time": end,
                            "price": price_decimal(price),
                            "label": label,
                        },
                    )
                activate_ground(ground=ground)

            if turf.status != Turf.Status.APPROVED:
                turf.status = Turf.Status.PENDING_REVIEW
                turf.save(update_fields=["status"])
                approve_turf(turf=turf, reviewer=admin)

            # A cashier per turf, so the staff flow is demo-able straight away.
            cashier, _ = User.objects.update_or_create(
                clerk_id=f"seed_cashier_{spec['slug']}",
                defaults={
                    "email": f"cashier.{spec['slug']}@turfapp.local",
                    "first_name": "Cashier",
                    "last_name": spec["area"],
                },
            )
            TurfMembership.objects.update_or_create(
                turf=turf,
                user=cashier,
                defaults={
                    "role": TurfMembership.Role.CASHIER,
                    "status": TurfMembership.Status.ACTIVE,
                    "invited_by": owner,
                },
            )

            self.stdout.write(
                f"Turf {turf.name} ({turf.area}): "
                f"{turf.grounds.count()} ground(s), status {turf.status}"
            )

    def seed_bookings(self) -> None:
        """One booking in each interesting state, so no screen starts empty.

        Built through the services, so the demo data is also a smoke test of the state
        machine: a transition that stopped working would fail the seed.
        """
        from datetime import timedelta

        from psycopg.types.range import TimestamptzRange

        from apps.bookings.models import Booking, BookingStatus
        from apps.bookings.services import (
            cancel_booking,
            complete_booking,
            confirm_booking,
            create_booking,
            mark_paid,
        )
        from apps.core.utils import DHAKA, now
        from apps.turfs.models import Ground, TurfMembership

        if Booking.objects.exists():
            self.stdout.write("Bookings already seeded; leaving them alone.")
            return

        User = get_user_model()
        players = list(User.objects.filter(clerk_id__startswith="seed_player_"))
        grounds = list(
            Ground.objects.filter(is_active=True).select_related("turf").order_by("turf__name")
        )
        if not players or not grounds:
            return

        def slot(ground, *, days_ahead: int, hour: int):
            """A slot start aligned to the top of a Dhaka hour, as availability offers."""
            moment = (now() + timedelta(days=days_ahead)).astimezone(DHAKA)
            return moment.replace(hour=hour, minute=0, second=0, microsecond=0)

        def staff_for(turf):
            membership = turf.memberships.filter(
                status=TurfMembership.Status.ACTIVE, role=TurfMembership.Role.OWNER
            ).first()
            return membership.user if membership else None

        # Players cycle so every ground gets a booking: there are more grounds than demo
        # players, and `zip` would stop at the shorter list and leave states uncovered.
        from itertools import cycle, islice

        pairs = list(zip(islice(cycle(players), len(grounds)), grounds, strict=False))

        made = []
        for index, (player, ground) in enumerate(pairs):
            sport_format = ground.sport_formats.first()
            if sport_format is None:
                continue
            try:
                booking = create_booking(
                    user=player,
                    ground=ground,
                    # A different day each time: one player cannot hold two slots at once.
                    start=slot(ground, days_ahead=index + 1, hour=19),
                    sport_format=sport_format,
                    notes="Seeded demo booking",
                )
            except Exception as exc:
                self.stdout.write(self.style.WARNING(f"Skipped a demo booking: {exc}"))
                continue
            made.append((booking, staff_for(ground.turf)))

        # Walk the first few through the state machine so every screen has content.
        for position, (booking, staff) in enumerate(made):
            if position == 0:
                continue  # left `reserved`, so the pending-confirmation queue is not empty
            confirm_booking(booking=booking, actor=staff, note="Seeded")
            if position == 1:
                continue  # left `confirmed`, awaiting payment at the counter
            mark_paid(booking=booking, actor=staff)
            if position == 2:
                continue  # left `paid`
            if position == 3:
                # Backdate it so completion is legal, then close it out.
                Booking.objects.filter(pk=booking.pk).update(
                    time_range=TimestamptzRange(
                        now() - timedelta(hours=3), now() - timedelta(hours=2)
                    )
                )
                booking.refresh_from_db()
                complete_booking(booking=booking)
            else:
                cancel_booking(
                    booking=booking, actor=staff, reason="Seeded cancellation", by_staff=True
                )

        counts = {
            status: Booking.objects.filter(status=status).count() for status in BookingStatus.values
        }
        self.stdout.write("Bookings: " + ", ".join(f"{n} {s}" for s, n in counts.items() if n))
