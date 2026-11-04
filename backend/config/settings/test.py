"""Test settings.

Kept deliberately hermetic: no Redis, no outbound network, fast password hashing,
and fake Clerk credentials so auth/webhook tests exercise real verification code
against locally generated keys instead of reaching clerk.com.
"""

from .base import *

DEBUG = False
ALLOWED_HOSTS = ["*", "testserver"]

# The production posture, so the permission matrix covers the schema routes for real
# rather than exempting them (Phase 11 step 4).
API_DOCS_PUBLIC = False

PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Local-memory cache: the JWKS cache must not leak between tests or need Redis.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "turfapp-test",
    }
}

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

MAILERS = {"default": {"BACKEND": "django.core.mail.backends.locmem.EmailBackend"}}

CLERK_FRONTEND_API_URL = "https://test-instance.clerk.accounts.dev"
CLERK_ISSUER = "https://test-instance.clerk.accounts.dev"
CLERK_SECRET_KEY = "sk_test_dummy"
CLERK_WEBHOOK_SIGNING_SECRET = "whsec_dGVzdHNlY3JldHRlc3RzZWNyZXR0ZXN0"
CLERK_AUTHORIZED_PARTIES = ["http://localhost:3000"]

LOGGING = {"version": 1, "disable_existing_loggers": False, "root": {"handlers": []}}
