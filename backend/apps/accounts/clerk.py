"""Clerk session-token verification.

Follows Clerk's documented manual verification procedure:

1. take the token from ``Authorization: Bearer <token>``
2. fetch the instance's JWKS (cached) and pick the key by ``kid``
3. verify an **RS256** signature and the ``exp`` / ``nbf`` claims with a small leeway
4. check ``iss`` equals the instance's Frontend API URL
5. check ``azp`` against an allowlist *when the claim is present* — Clerk only sets it
   if the originating request carried an ``Origin`` header

Session tokens are claim version ``v2``: organisation data arrives as a compact ``o``
object (``o.id`` / ``o.rol`` / ``o.slg`` / ``o.per``) rather than v1's ``org_*`` claims.

Deliberately hand-rolled on PyJWT rather than using ``clerk-backend-api`` (DECISIONS
D15): it keeps JWKS mockable in tests, adds no dependency, and matches the project brief.
"""

from __future__ import annotations

import logging
from typing import Any

import jwt
import requests
from django.conf import settings
from django.core.cache import cache
from jwt import PyJWKSet

logger = logging.getLogger(__name__)

JWKS_CACHE_KEY = "clerk:jwks"
JWKS_REQUEST_TIMEOUT_SECONDS = 5
ALLOWED_ALGORITHMS = ["RS256"]


class ClerkConfigurationError(RuntimeError):
    """The Clerk instance is not configured (missing frontend API URL)."""


class ClerkTokenError(Exception):
    """The token is missing, malformed, expired or otherwise untrustworthy."""


def jwks_url() -> str:
    base = (settings.CLERK_FRONTEND_API_URL or "").rstrip("/")
    if not base:
        raise ClerkConfigurationError(
            "CLERK_FRONTEND_API_URL is not set; cannot verify Clerk session tokens."
        )
    return f"{base}/.well-known/jwks.json"


def _fetch_jwks() -> dict[str, Any]:
    response = requests.get(jwks_url(), timeout=JWKS_REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.json()


def get_jwks(*, force_refresh: bool = False) -> dict[str, Any]:
    """Return the instance JWKS, cached for ``CLERK_JWKS_CACHE_SECONDS``."""
    if not force_refresh:
        cached = cache.get(JWKS_CACHE_KEY)
        if cached:
            return cached

    jwks = _fetch_jwks()
    cache.set(JWKS_CACHE_KEY, jwks, timeout=settings.CLERK_JWKS_CACHE_SECONDS)
    return jwks


def _signing_key(token: str, *, force_refresh: bool = False):
    """Find the signing key for the token's ``kid``.

    On an unknown ``kid`` the JWKS is re-fetched once — that is the normal path right
    after Clerk rotates keys, and it must not turn into a per-request fetch storm.
    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise ClerkTokenError("Malformed token header.") from exc

    kid = header.get("kid")
    if not kid:
        raise ClerkTokenError("Token header has no 'kid'.")
    if header.get("alg") not in ALLOWED_ALGORITHMS:
        raise ClerkTokenError(f"Unexpected token algorithm {header.get('alg')!r}.")

    key_set = PyJWKSet.from_dict(get_jwks(force_refresh=force_refresh))
    for key in key_set.keys:
        if key.key_id == kid:
            return key.key

    if not force_refresh:
        return _signing_key(token, force_refresh=True)
    raise ClerkTokenError(f"No signing key matches kid {kid!r}.")


def verify_token(token: str) -> dict[str, Any]:
    """Verify a Clerk session token and return its claims.

    Raises ``ClerkTokenError`` for anything that makes the token untrustworthy.
    """
    if not token:
        raise ClerkTokenError("Empty token.")

    key = _signing_key(token)

    try:
        claims = jwt.decode(
            token,
            key=key,
            algorithms=ALLOWED_ALGORITHMS,
            issuer=settings.CLERK_ISSUER or None,
            leeway=settings.CLERK_JWT_LEEWAY_SECONDS,
            options={
                "require": ["exp", "iat", "sub"],
                "verify_exp": True,
                "verify_nbf": True,
                "verify_iat": True,
                "verify_iss": bool(settings.CLERK_ISSUER),
                # Clerk session tokens carry no `aud`; `azp` is checked below instead.
                "verify_aud": False,
            },
        )
    except jwt.ExpiredSignatureError as exc:
        raise ClerkTokenError("Token has expired.") from exc
    except jwt.ImmatureSignatureError as exc:
        raise ClerkTokenError("Token is not valid yet.") from exc
    except jwt.InvalidIssuerError as exc:
        raise ClerkTokenError("Token issuer is not this Clerk instance.") from exc
    except jwt.MissingRequiredClaimError as exc:
        raise ClerkTokenError(f"Token is missing a required claim: {exc.claim}.") from exc
    except jwt.PyJWTError as exc:
        raise ClerkTokenError("Token signature is invalid.") from exc

    _verify_authorized_party(claims)

    # Organisations without personal accounts can issue tokens for a session that has
    # not finished selecting an organisation; such a session is not usable yet.
    if claims.get("sts") == "pending":
        raise ClerkTokenError("Session is pending and cannot be used yet.")

    if not claims.get("sub"):
        raise ClerkTokenError("Token has no subject.")

    return claims


def _verify_authorized_party(claims: dict[str, Any]) -> None:
    azp = claims.get("azp")
    if not azp:
        # Documented behaviour: the claim is absent when the originating request had no
        # Origin header, and absence is not by itself a failure.
        return

    allowed = [party.rstrip("/") for party in settings.CLERK_AUTHORIZED_PARTIES if party]
    if allowed and azp.rstrip("/") not in allowed:
        raise ClerkTokenError(f"Authorized party {azp!r} is not allowed.")


BACKEND_API_BASE_URL = "https://api.clerk.com/v1"
BACKEND_API_TIMEOUT_SECONDS = 5


def fetch_clerk_user(clerk_id: str) -> dict[str, Any] | None:
    """Read one user from Clerk's Backend API, or ``None`` if it cannot be read.

    Needed because a **session token carries no identity claims** — only ``sub``,
    ``sid``, ``iss`` and friends. The webhook is the normal way names and emails arrive,
    but it can be unconfigured (there is no public URL in local development), late, or
    have failed, which would leave the account nameless everywhere in the UI.

    Returns ``None`` rather than raising: this runs on the authentication path, and a
    Clerk outage must not sign everybody out.
    """
    secret = settings.CLERK_SECRET_KEY
    if not secret:
        return None

    try:
        response = requests.get(
            f"{BACKEND_API_BASE_URL}/users/{clerk_id}",
            headers={"Authorization": f"Bearer {secret}"},
            timeout=BACKEND_API_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning(
            "Could not read user from Clerk's Backend API: %s", exc, extra={"clerk_id": clerk_id}
        )
        return None

    return payload if isinstance(payload, dict) else None
