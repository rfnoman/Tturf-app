"""Tests for Clerk session-token verification and the DRF authentication class."""

from __future__ import annotations

import time

import pytest
import requests
from django.urls import reverse
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient

from apps.accounts.clerk import ClerkConfigurationError, ClerkTokenError, jwks_url, verify_token
from apps.accounts.models import User

from .conftest import OTHER_KID, TEST_KID, jwks_for

pytestmark = pytest.mark.django_db


# ---------------------------------------------------------------------------
# verify_token
# ---------------------------------------------------------------------------


def test_valid_token_returns_claims(patch_jwks, make_token):
    patch_jwks()
    claims = verify_token(make_token(sub="user_valid"))

    assert claims["sub"] == "user_valid"
    assert claims["v"] == 2


def test_expired_token_is_rejected(patch_jwks, make_token):
    patch_jwks()
    with pytest.raises(ClerkTokenError, match="expired"):
        verify_token(make_token(expires_in=-120))


def test_token_within_leeway_is_accepted(patch_jwks, make_token, settings):
    """Clerk's own verifier allows 5s of skew; ours must match."""
    patch_jwks()
    settings.CLERK_JWT_LEEWAY_SECONDS = 5

    token = make_token(expires_in=-2)
    assert verify_token(token)["sub"]


def test_not_yet_valid_token_is_rejected(patch_jwks, make_token):
    patch_jwks()
    future = int(time.time()) + 600
    with pytest.raises(ClerkTokenError, match="not valid yet"):
        verify_token(make_token(not_before=future, issued_at=future, expires_in=1200))


def test_wrong_issuer_is_rejected(patch_jwks, make_token):
    patch_jwks()
    with pytest.raises(ClerkTokenError, match="issuer"):
        verify_token(make_token(issuer="https://evil.clerk.accounts.dev"))


def test_unlisted_authorized_party_is_rejected(patch_jwks, make_token):
    patch_jwks()
    with pytest.raises(ClerkTokenError, match="Authorized party"):
        verify_token(make_token(azp="https://attacker.example"))


def test_missing_azp_is_allowed(patch_jwks, make_token):
    """Clerk omits `azp` when the originating request had no Origin header."""
    patch_jwks()
    assert verify_token(make_token(azp=None))["sub"]


def test_token_signed_by_unknown_key_is_rejected(patch_jwks, make_token, other_rsa_key):
    """Right kid, wrong signer: the signature must fail."""
    patch_jwks()
    with pytest.raises(ClerkTokenError, match="signature"):
        verify_token(make_token(key=other_rsa_key, kid=TEST_KID))


def test_tampered_payload_is_rejected(patch_jwks, make_token):
    patch_jwks()
    header, payload, signature = make_token().split(".")
    tampered = f"{header}.{payload[:-4]}AAAA.{signature}"
    with pytest.raises(ClerkTokenError):
        verify_token(tampered)


def test_unsigned_token_is_rejected(patch_jwks, make_token):
    """A token claiming alg=none must never be accepted."""
    patch_jwks()
    import jwt as pyjwt

    unsigned = pyjwt.encode(
        {"sub": "user_x"}, key=None, algorithm="none", headers={"kid": TEST_KID}
    )
    with pytest.raises(ClerkTokenError, match="algorithm"):
        verify_token(unsigned)


def test_token_without_kid_is_rejected(patch_jwks, make_token, rsa_key):
    patch_jwks()
    import jwt as pyjwt

    token = pyjwt.encode({"sub": "user_x"}, key=rsa_key, algorithm="RS256")
    with pytest.raises(ClerkTokenError, match="kid"):
        verify_token(token)


def test_pending_session_is_rejected(patch_jwks, make_token):
    patch_jwks()
    with pytest.raises(ClerkTokenError, match="pending"):
        verify_token(make_token(sts="pending"))


def test_malformed_token_is_rejected(patch_jwks):
    patch_jwks()
    with pytest.raises(ClerkTokenError):
        verify_token("not-a-jwt")


def test_empty_token_is_rejected():
    with pytest.raises(ClerkTokenError, match="Empty"):
        verify_token("")


def test_missing_clerk_configuration_raises(settings, make_token):
    settings.CLERK_FRONTEND_API_URL = ""
    with pytest.raises(ClerkConfigurationError):
        verify_token(make_token())


def test_jwks_url_shape(settings):
    settings.CLERK_FRONTEND_API_URL = "https://example.clerk.accounts.dev"
    assert jwks_url() == "https://example.clerk.accounts.dev/.well-known/jwks.json"


# ---------------------------------------------------------------------------
# JWKS caching and rotation
# ---------------------------------------------------------------------------


def test_jwks_is_cached_across_calls(patch_jwks, make_token):
    calls = patch_jwks()
    verify_token(make_token())
    verify_token(make_token())

    assert calls["count"] == 1


def test_unknown_kid_refetches_jwks_once(patch_jwks, make_token, rsa_key, other_rsa_key):
    """After a Clerk key rotation the first token with a new kid must still verify."""
    calls = patch_jwks(jwks_for({TEST_KID: rsa_key, OTHER_KID: other_rsa_key}))

    # Warm the cache with a document that lacks the rotated key.
    verify_token(make_token(kid=TEST_KID))
    assert calls["count"] == 1

    claims = verify_token(make_token(key=other_rsa_key, kid=OTHER_KID))
    assert claims["sub"]


def test_kid_absent_even_after_refresh_is_rejected(patch_jwks, make_token, other_rsa_key):
    calls = patch_jwks()
    with pytest.raises(ClerkTokenError, match="No signing key"):
        verify_token(make_token(key=other_rsa_key, kid="never-existed"))

    # One warm fetch plus exactly one forced refresh: no fetch storm.
    assert calls["count"] == 2


# ---------------------------------------------------------------------------
# DRF integration via /api/v1/me
# ---------------------------------------------------------------------------


def test_me_requires_authentication():
    response = APIClient().get(reverse("v1:me"))
    assert response.status_code == 401


def test_me_returns_user_and_creates_the_row(patch_jwks, make_token):
    patch_jwks()
    client = APIClient()
    token = make_token(sub="user_first_call")

    response = client.get(reverse("v1:me"), HTTP_AUTHORIZATION=f"Bearer {token}")

    assert response.status_code == 200
    assert response.data["clerk_id"] == "user_first_call"
    # The webhook may be late or unconfigured; first authenticated call must still work.
    assert User.objects.filter(clerk_id="user_first_call").exists()


def test_me_reuses_the_existing_user(patch_jwks, make_token):
    patch_jwks()
    user = User.objects.create_user(clerk_id="user_existing", email="player@example.com")
    client = APIClient()

    response = client.get(
        reverse("v1:me"),
        HTTP_AUTHORIZATION=f"Bearer {make_token(sub='user_existing')}",
    )

    assert response.status_code == 200
    assert response.data["id"] == str(user.id)
    assert User.objects.filter(clerk_id="user_existing").count() == 1


def test_inactive_user_is_refused(patch_jwks, make_token):
    patch_jwks()
    User.objects.create_user(clerk_id="user_gone", email="gone@example.com", is_active=False)

    response = APIClient().get(
        reverse("v1:me"),
        HTTP_AUTHORIZATION=f"Bearer {make_token(sub='user_gone')}",
    )

    assert response.status_code == 401
    assert "inactive" in str(response.data["detail"]).lower()


def test_bad_token_returns_401(patch_jwks, make_token):
    patch_jwks()
    response = APIClient().get(
        reverse("v1:me"),
        HTTP_AUTHORIZATION=f"Bearer {make_token(expires_in=-300)}",
    )
    assert response.status_code == 401


def test_malformed_authorization_header_returns_401(patch_jwks):
    patch_jwks()
    response = APIClient().get(reverse("v1:me"), HTTP_AUTHORIZATION="Bearer")
    assert response.status_code == 401


def test_non_bearer_scheme_is_ignored_by_this_class(patch_jwks):
    """A Basic header is not ours to reject; it must fall through as unauthenticated."""
    patch_jwks()
    response = APIClient().get(reverse("v1:me"), HTTP_AUTHORIZATION="Basic abc123")
    assert response.status_code == 401


def test_jwks_network_failure_surfaces_as_auth_failure(monkeypatch, make_token):
    def boom():
        raise requests.ConnectionError("clerk unreachable")

    monkeypatch.setattr("apps.accounts.clerk._fetch_jwks", boom)

    from rest_framework.test import APIRequestFactory

    from apps.accounts.authentication import ClerkJWTAuthentication

    request = APIRequestFactory().get("/api/v1/me", HTTP_AUTHORIZATION=f"Bearer {make_token()}")
    with pytest.raises(AuthenticationFailed, match="retry"):
        ClerkJWTAuthentication().authenticate(request)
