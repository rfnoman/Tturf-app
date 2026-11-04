"""Production settings. Final hosting choices land in Phase 11 (DECISIONS D11)."""

from .base import *
from .base import MIDDLEWARE, STORAGES, env

DEBUG = False
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS")

SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=60 * 60 * 24 * 365)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
X_FRAME_OPTIONS = "DENY"
# A complete map of every endpoint, payload and parameter is the first thing anybody
# probing the API would want. The people who need it have accounts (Phase 11 step 4).
API_DOCS_PUBLIC = env.bool("API_DOCS_PUBLIC", default=False)
# Behind the admin password is every booking, payment and player record (D64).
ADMIN_REQUIRES_OTP = env.bool("ADMIN_REQUIRES_OTP", default=True)

# WhiteNoise serves collected static files in production; in dev the staticfiles app does.
MIDDLEWARE = MIDDLEWARE.copy()
MIDDLEWARE.insert(
    MIDDLEWARE.index("django.middleware.security.SecurityMiddleware") + 1,
    "whitenoise.middleware.WhiteNoiseMiddleware",
)

STORAGES = {
    **STORAGES,
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Connection pooling is psycopg3-only and wants Celery >= 5.6 for post-fork safety.
DATABASES["default"]["OPTIONS"] = {"pool": env.bool("POSTGRES_POOL", default=True)}
DATABASES["default"]["CONN_MAX_AGE"] = env.int("POSTGRES_CONN_MAX_AGE", default=60)
