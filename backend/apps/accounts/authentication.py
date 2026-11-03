"""DRF authentication against Clerk session tokens."""

from __future__ import annotations

import logging

import requests
from rest_framework import authentication, exceptions

from .clerk import ClerkConfigurationError, ClerkTokenError, verify_token
from .services import get_or_create_user_from_claims

logger = logging.getLogger(__name__)

AUTH_HEADER_PREFIX = "Bearer"


class ClerkJWTAuthentication(authentication.BaseAuthentication):
    """Authenticate ``Authorization: Bearer <clerk session token>``.

    Returns ``None`` when no bearer token is present so that public endpoints and other
    authentication classes still work; raises only when a token was supplied and is bad.
    """

    keyword = AUTH_HEADER_PREFIX

    def authenticate(self, request):
        token = self.get_token(request)
        if token is None:
            return None

        try:
            claims = verify_token(token)
        except ClerkTokenError as exc:
            raise exceptions.AuthenticationFailed(str(exc)) from exc
        except ClerkConfigurationError as exc:
            logger.error("Clerk is not configured: %s", exc)
            raise exceptions.AuthenticationFailed("Authentication is not configured.") from exc
        except requests.RequestException as exc:
            logger.warning("Could not reach Clerk JWKS: %s", exc)
            raise exceptions.AuthenticationFailed(
                "Could not verify credentials, please retry."
            ) from exc

        user = get_or_create_user_from_claims(claims)
        if not user.is_active:
            raise exceptions.AuthenticationFailed("This account is inactive.")

        # Claims are handy downstream (session id, org context) without re-decoding.
        request.clerk_claims = claims
        return (user, claims)

    def authenticate_header(self, request) -> str:
        return self.keyword

    @staticmethod
    def get_token(request) -> str | None:
        header = authentication.get_authorization_header(request).decode("latin-1")
        if not header:
            return None

        parts = header.split()
        if parts[0].lower() != AUTH_HEADER_PREFIX.lower():
            # Some other scheme (e.g. Basic); let another class handle it.
            return None
        if len(parts) != 2:
            raise exceptions.AuthenticationFailed(
                "Invalid Authorization header; expected 'Bearer <token>'."
            )
        return parts[1]
