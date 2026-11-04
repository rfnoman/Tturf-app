"""Every route, against every role that must not reach it (Phase 11 step 4).

167 routes were added by hand over eleven phases. The failure mode is silent: one
missing `IsAuthenticated` is a data leak that no feature test notices, because every
feature test is already signed in as somebody.

So this walks the URL conf itself rather than a list somebody maintains. A route added
tomorrow is covered tomorrow, and the only way to exempt one is to name it in
`PUBLIC_ROUTES` below — which is a line in a diff a reviewer can argue with.
"""

from __future__ import annotations

import re
import uuid

import pytest
from django.urls import get_resolver
from rest_framework.test import APIClient

from apps.accounts.tests.factories import UserFactory

pytestmark = pytest.mark.django_db

#: Routes that are public **on purpose**, each with the reason.
PUBLIC_ROUTES = {
    "api/v1/health": "liveness probe",
    "api/v1/config": "business rules the signed-out shell needs to render",
    "api/v1/webhooks/clerk": "Clerk calls it; authenticated by signature, not by session",
    "api/v1/public/matches/<uuid:match_id>/scorecard": "a locked card is a shareable link (D43)",
    "api/v1/product-categories": "the store's shop window",
    "api/v1/turfs/<slug:slug>/products": "the store's shop window",
    "api/v1/store/products": "the store's shop window",
    "api/v1/payments/ipn/<str:provider>": "the gateway calls it; authenticated by validation (D57)",
}

#: Values to stand in for path converters, so a route can actually be requested.
SAMPLES = {
    "uuid": lambda: str(uuid.uuid4()),
    "slug": lambda: "nothing-here",
    "int": lambda: "1",
    "str": lambda: "nothing-here",
    "path": lambda: "nothing-here",
}

#: `path()` writes `<uuid:match_id>`; `SimpleRouter` writes `^matches/(?P<pk>[^/.]+)$`.
#: Both shapes appear in the URL conf, so both have to be filled in.
CONVERTER = re.compile(r"<(?:(\w+):)?(\w+)>")
REGEX_GROUP = re.compile(r"\(\?P<(\w+)>[^)]*\)")


def all_routes():
    """Every `/api/v1/` route in the URL conf, as (pattern, view class)."""

    def walk(resolver, prefix=""):
        for entry in resolver.url_patterns:
            if hasattr(entry, "url_patterns"):
                yield from walk(entry, prefix + str(entry.pattern))
            else:
                yield prefix + str(entry.pattern), entry.callback

    return [row for row in walk(get_resolver()) if row[0].startswith("api/v1")]


def concrete(pattern: str) -> str:
    """Turn a route pattern into a URL that can actually be requested.

    A pattern filled in wrongly 404s, and 404 is not in the set these tests accept — so
    a broken URL here fails loudly rather than passing for the wrong reason, which is
    the failure mode that would make this whole file worthless.
    """

    def swap(match):
        converter = match.group(1) or "str"
        return SAMPLES.get(converter, SAMPLES["str"])()

    def swap_group(match):
        # Router patterns name their capture but not its type; a UUID satisfies both the
        # UUID lookups and the slug ones, since nothing here validates the shape before
        # checking permissions.
        return "nothing-here" if match.group(1) == "slug" else str(uuid.uuid4())

    filled = CONVERTER.sub(swap, pattern)
    filled = REGEX_GROUP.sub(swap_group, filled)
    return "/" + filled.replace("^", "").replace("$", "")


PROTECTED = [row for row in all_routes() if row[0] not in PUBLIC_ROUTES]


class TestAnonymousAccess:
    @pytest.mark.parametrize("pattern,view", PROTECTED, ids=lambda row: str(row))
    def test_a_signed_out_visitor_is_refused(self, pattern, view):
        """401 or 403 — never a body, and never a 500 from code that assumed a user."""
        response = APIClient().get(concrete(pattern))

        assert response.status_code in {401, 403}, (
            f"{pattern} answered {response.status_code} to an anonymous GET. "
            "Either it needs a permission class, or it belongs in PUBLIC_ROUTES with a reason."
        )


class TestPublicRoutesAreDeliberate:
    def test_every_open_route_is_listed_with_a_reason(self):
        """A new `AllowAny` has to be argued for in a diff, not discovered in a log."""
        open_now = set()
        for pattern, view in all_routes():
            cls = getattr(view, "cls", None) or getattr(view, "view_class", None)
            names = {p.__name__ for p in getattr(cls, "permission_classes", []) or []}
            if "AllowAny" in names:
                open_now.add(pattern)

        assert open_now == set(PUBLIC_ROUTES), (
            "Routes opened without a reason: "
            f"{sorted(open_now - set(PUBLIC_ROUTES))}; "
            "routes listed as public but no longer open: "
            f"{sorted(set(PUBLIC_ROUTES) - open_now)}"
        )


class TestAdminRoutes:
    """A signed-in player is not an admin, and the difference has to be enforced."""

    @pytest.mark.parametrize(
        "pattern,view",
        [row for row in PROTECTED if "/admin/" in row[0] or row[0].startswith("api/v1/admin")],
        ids=lambda row: str(row),
    )
    def test_an_ordinary_player_is_refused(self, pattern, view):
        client = APIClient()
        client.force_authenticate(UserFactory())
        response = client.get(concrete(pattern))

        assert response.status_code in {403, 404}, (
            f"{pattern} answered {response.status_code} to an ordinary player."
        )


class TestApiDocumentation:
    """The schema is open locally and closed once deployed (Phase 11 step 4).

    The anonymous-access test above already proves it is closed here, because the test
    settings use the production posture. These pin the other half: that it can still be
    opened for local work, and that opening it is a per-request decision rather than
    something baked in at import.
    """

    def test_a_platform_admin_can_always_read_it(self):
        admin = UserFactory(is_platform_admin=True)
        client = APIClient()
        client.force_authenticate(admin)

        assert client.get("/api/v1/schema/").status_code == 200

    def test_can_be_opened_for_local_work(self, settings):
        settings.API_DOCS_PUBLIC = True

        assert APIClient().get("/api/v1/schema/").status_code == 200


class TestPersonalDataInPayloads:
    """A player's email is not a display name (Phase 11 step 4).

    Every roster row, board card and timeline entry falls back to *something* when a
    player has not set a name. That fallback used to be `user.email`, so a player who
    had signed up and not finished onboarding had their email shown to everybody who
    could see the match — in eleven places, with nothing in the UI to hint at it.
    """

    def test_an_unnamed_player_is_not_identified_by_their_email(self):
        from apps.core.utils import player_label

        stranger = UserFactory(first_name="", last_name="", email="private@example.com")

        label = player_label(stranger)

        assert "@" not in label
        assert label == "Player"

    def test_the_same_holds_for_a_player_who_has_a_profile(self):
        """The layer the first fix missed.

        `player_label` prefers `profile.name`, and `PlayerProfile.name` had the same
        email fallback underneath it — so a player who had started onboarding but set no
        name was still being identified by their email everywhere.
        """
        from apps.core.utils import player_label
        from apps.players.services import get_or_create_profile

        stranger = UserFactory(first_name="", last_name="", email="private@example.com")
        profile = get_or_create_profile(stranger)
        profile.display_name = ""
        profile.save(update_fields=["display_name"])

        assert "@" not in player_label(stranger)
        assert "@" not in profile.name

    def test_a_named_player_is_called_by_their_name(self):
        from apps.core.utils import player_label

        assert player_label(UserFactory(first_name="Rafi", last_name="Ahmed")) == "Rafi Ahmed"

    def test_no_serializer_falls_back_to_an_email(self):
        """The grep that found the leak, kept as a test so it cannot come back."""
        import pathlib

        root = pathlib.Path(__file__).resolve().parents[3]
        offenders = [
            f"{path.relative_to(root)}:{number}"
            for path in root.glob("apps/*/serializers.py")
            for number, line in enumerate(path.read_text().splitlines(), start=1)
            if ".email)" in line or "or user.email" in line
        ]

        assert offenders == [], f"An email is being used as a display name in {offenders}"


class TestUploadLimits:
    """An image upload is a request to allocate memory on somebody else's server."""

    def test_an_oversized_file_is_refused(self):
        from django.core.exceptions import ValidationError

        from apps.core.validators import MAX_IMAGE_BYTES, validate_image_upload

        class Huge:
            size = MAX_IMAGE_BYTES + 1
            image = None

        with pytest.raises(ValidationError) as refusal:
            validate_image_upload(Huge())

        assert refusal.value.code == "image_too_large"
        # The message has to be actionable: "too big" tells somebody holding a photo
        # that looks fine to them nothing at all.
        assert "MB" in str(refusal.value.messages[0])

    def test_a_decompression_bomb_is_refused(self):
        """Small on disk, enormous in memory — the attack `ImageField` does not stop."""
        from django.core.exceptions import ValidationError

        from apps.core.validators import MAX_IMAGE_PIXELS, validate_image_upload

        class Bomb:
            size = 50_000  # a few kilobytes of highly compressible pixels

            class image:
                width = MAX_IMAGE_PIXELS + 1
                height = MAX_IMAGE_PIXELS + 1

        with pytest.raises(ValidationError):
            validate_image_upload(Bomb())

    def test_an_ordinary_photo_passes(self):
        from apps.core.validators import validate_image_upload

        class Phone:
            size = 2_400_000

            class image:
                width = 3024
                height = 4032

        validate_image_upload(Phone())  # does not raise
