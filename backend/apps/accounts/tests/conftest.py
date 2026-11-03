"""Test fixtures for Clerk authentication.

Tokens are signed with a keypair generated in-process and served through a fake JWKS,
so the real verification path (signature, claims, key lookup, cache) is exercised end
to end without any network access to clerk.com.
"""

from __future__ import annotations

import json
import time
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.core.cache import cache

TEST_KID = "test-key-1"
OTHER_KID = "rotated-key-2"


def _make_keypair():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="session")
def rsa_key():
    return _make_keypair()


@pytest.fixture(scope="session")
def other_rsa_key():
    """A second key, for rotation and wrong-signer cases."""
    return _make_keypair()


def jwks_for(keys: dict[str, Any]) -> dict[str, Any]:
    """Build a JWKS document from ``{kid: private_key}``."""
    entries = []
    for kid, key in keys.items():
        jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(key.public_key()))
        jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
        entries.append(jwk)
    return {"keys": entries}


@pytest.fixture
def jwks(rsa_key):
    return jwks_for({TEST_KID: rsa_key})


@pytest.fixture(autouse=True)
def clear_jwks_cache():
    """The JWKS cache must not leak between tests."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture
def make_token(rsa_key):
    """Build a signed Clerk-style session token.

    Defaults produce a valid v2 session token for this instance; every claim can be
    overridden to construct the failure cases.
    """

    def _make(
        *,
        key=None,
        kid: str = TEST_KID,
        sub: str = "user_2abcDEF",
        issuer: str | None = None,
        azp: str | None = "http://localhost:3000",
        expires_in: int = 60,
        issued_at: int | None = None,
        not_before: int | None = None,
        algorithm: str = "RS256",
        **extra_claims,
    ) -> str:
        now = int(time.time())
        claims: dict[str, Any] = {
            "sub": sub,
            "iss": settings.CLERK_ISSUER if issuer is None else issuer,
            "iat": now if issued_at is None else issued_at,
            "nbf": now if not_before is None else not_before,
            "exp": now + expires_in,
            "sid": "sess_2abcDEF",
            "jti": "jti_abc123",
            "v": 2,
        }
        if azp is not None:
            claims["azp"] = azp
        claims.update(extra_claims)

        return jwt.encode(
            claims,
            key=key or rsa_key,
            algorithm=algorithm,
            headers={"kid": kid},
        )

    return _make


@pytest.fixture
def patch_jwks(monkeypatch, jwks):
    """Serve a JWKS without network access, and count how often it is fetched."""
    calls = {"count": 0}

    def _install(document: dict[str, Any] | None = None):
        doc = jwks if document is None else document

        def fake_fetch() -> dict[str, Any]:
            calls["count"] += 1
            return doc

        monkeypatch.setattr("apps.accounts.clerk._fetch_jwks", fake_fetch)
        return calls

    _install.calls = calls  # type: ignore[attr-defined]
    return _install
