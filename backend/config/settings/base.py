"""
Settings shared by every environment.

Conventions (see CLAUDE.md):
- Time is stored in UTC (``USE_TZ=True``) and displayed in Dhaka time.
- Money is ``Decimal``, never float.
- Configurable business rules live here as constants (or later in a ``PlatformSetting``
  row) and are never hard-coded inline in services.
"""

from __future__ import annotations

import sys
from pathlib import Path

import environ
from celery.schedules import crontab

# backend/config/settings/base.py -> backend/
BASE_DIR = Path(__file__).resolve().parents[2]

env = environ.Env()
# Read backend/.env when present. Real environments inject variables directly.
environ.Env.read_env(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
SECRET_KEY = env("DJANGO_SECRET_KEY", default="insecure-dev-key-change-me")
DEBUG = env.bool("DJANGO_DEBUG", default=False)
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

AUTH_USER_MODEL = "accounts.User"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.gis",
    "django.contrib.postgres",
]

THIRD_PARTY_APPS = [
    # A second factor for the Django admin, and nothing else — player and owner accounts
    # authenticate through Clerk, which has its own (Phase 11 step 4, DECISIONS D64).
    "django_otp",
    "django_otp.plugins.otp_totp",
    "rest_framework",
    "drf_spectacular",
    "corsheaders",
    "django_filters",
]

LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.sports",
    "apps.players",
    "apps.turfs",
    "apps.notifications",
    "apps.payments",
    "apps.bookings",
    "apps.matches",
    "apps.scoring",
    "apps.ratings",
    "apps.inventory",
    "apps.store",
    "apps.fitness",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Must follow AuthenticationMiddleware: it decorates `request.user` with the
    # verified-device state the admin login then checks (Phase 11 step 4).
    "django_otp.middleware.OTPMiddleware",
    # Resolves the request language from `Accept-Language`, which the frontend sets from
    # its own locale cookie. Catalogue labels (sports, product categories) are served in
    # that language; nothing else in the API is translated (DECISIONS D63).
    "django.middleware.locale.LocaleMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# ---------------------------------------------------------------------------
# Database — PostGIS
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.contrib.gis.db.backends.postgis",
        "NAME": env("POSTGRES_DB", default="turf"),
        "USER": env("POSTGRES_USER", default="turf"),
        "PASSWORD": env("POSTGRES_PASSWORD", default="turf"),
        "HOST": env("POSTGRES_HOST", default="127.0.0.1"),
        "PORT": env.int("POSTGRES_PORT", default=5432),
    }
}

# GeoDjango loads GEOS/GDAL through ctypes. ``ctypes.util.find_library`` does not search
# Homebrew's /opt/homebrew/lib on Apple Silicon, so point at the unversioned symlinks
# (stable across brew upgrades). Linux/Docker resolves them normally and is unaffected.
if sys.platform == "darwin":
    GDAL_LIBRARY_PATH = env("GDAL_LIBRARY_PATH", default="/opt/homebrew/lib/libgdal.dylib")
    GEOS_LIBRARY_PATH = env("GEOS_LIBRARY_PATH", default="/opt/homebrew/lib/libgeos_c.dylib")

# ---------------------------------------------------------------------------
# Cache / Celery (Redis)
# ---------------------------------------------------------------------------
REDIS_URL = env("REDIS_URL", default="redis://127.0.0.1:6379/0")

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": REDIS_URL,
    }
}

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default=REDIS_URL)
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=REDIS_URL)
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
# Celery schedules run on UTC; business rules convert to Dhaka time where it matters.
CELERY_TIMEZONE = "UTC"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 10 * 60

# Periodic tasks. Phase 03 registers reservation expiry and booking completion; later
# phases add vote close and reminders.
CELERY_BEAT_SCHEDULE: dict[str, dict] = {
    "expire-overdue-bookings": {
        "task": "bookings.expire_overdue",
        # Every minute: an expiry deadline is only useful if the slot is actually
        # released close to it, so somebody else can take it.
        "schedule": 60.0,
    },
    "complete-finished-bookings": {
        "task": "bookings.complete_finished",
        # Every five minutes. Completion only has to beat the player noticing.
        "schedule": 300.0,
    },
    "expire-pending-match-requests": {
        "task": "matches.expire_pending",
        # Requests and invites expire at match start (DOMAIN §6).
        "schedule": 120.0,
    },
    "advance-match-statuses": {
        "task": "matches.advance_statuses",
        "schedule": 120.0,
    },
    "auto-confirm-scorecards": {
        "task": "scoring.auto_confirm",
        # Hourly: the window is 24h, so minute-level precision buys nothing.
        "schedule": 3600.0,
    },
    "close-motm-voting": {
        "task": "scoring.close_motm",
        "schedule": 3600.0,
    },
    "remind-before-store-cutoff": {
        "task": "store.remind_before_cutoff",
        # Hourly: the window is three hours wide, so this cannot miss one.
        "schedule": 3600.0,
    },
    "flag-late-turf-deliveries": {
        "task": "store.flag_late_turf_deliveries",
        "schedule": 1800.0,
    },
    "match-day-summary": {
        "task": "fitness.match_day_summary",
        # Hourly, but only fires for matches today and only once per player.
        "schedule": 3600.0,
    },
    "hydration-reminder": {
        "task": "fitness.hydration_reminder",
        # Every ten minutes: "two hours before" has to mean roughly that.
        "schedule": 600.0,
    },
    "recovery-tip": {
        "task": "fitness.recovery_tip",
        "schedule": 1800.0,
    },
    "weekly-recap": {
        "task": "fitness.weekly_recap",
        # Saturday morning, when the Bangladeshi week turns over (DECISIONS D56).
        "schedule": crontab(hour=9, minute=0, day_of_week="sat"),
    },
    "rebuild-leaderboards": {
        "task": "ratings.rebuild_leaderboards",
        # Nightly at 03:00 Dhaka — the boards move once a day at most and this is the
        # quietest hour for a job that rewrites every row.
        "schedule": crontab(hour=3, minute=0),
    },
}

# ---------------------------------------------------------------------------
# Password validation (Clerk owns authentication; these apply to Django admin users)
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# i18n / time
# ---------------------------------------------------------------------------
#: Whether the OpenAPI schema and its two documentation UIs are readable without an
#: account. True in development, so `npm run gen:api` needs no credentials; the
#: production settings turn it off (Phase 11 step 4).
API_DOCS_PUBLIC = env.bool("API_DOCS_PUBLIC", default=True)

#: Whether the Django admin demands a TOTP code as well as a password. Off locally,
#: where it is friction with nothing to protect; on in production (Phase 11 step 4).
ADMIN_REQUIRES_OTP = env.bool("ADMIN_REQUIRES_OTP", default=False)

#: Django's own ceiling on a request body, so an oversized upload is refused before
#: anything parses it. `apps/core/validators.py` then bounds the image itself
#: (Phase 11 step 4); this is the cruder guard that runs first.
DATA_UPLOAD_MAX_MEMORY_SIZE = env.int("DATA_UPLOAD_MAX_MEMORY_SIZE", default=6 * 1024 * 1024)
FILE_UPLOAD_MAX_MEMORY_SIZE = env.int("FILE_UPLOAD_MAX_MEMORY_SIZE", default=2 * 1024 * 1024)

LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("bn", "Bangla")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Asia/Dhaka"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static / media
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
# Manifest storage requires a collectstatic run, so it is enabled in prod only.
# Media moves to S3-compatible storage in Phase 02 (django-storages).
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# ---------------------------------------------------------------------------
# DRF + OpenAPI
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.accounts.authentication.ClerkJWTAuthentication",
        # Session auth keeps the browsable API and Django admin usable in dev.
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_PAGINATION_CLASS": "apps.core.pagination.DefaultPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": ["django_filters.rest_framework.DjangoFilterBackend"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "TEST_REQUEST_DEFAULT_FORMAT": "json",
    # Rate limiting (Phase 11 step 4). Nothing was metered before this, so one script
    # could fill a player's inbox with join requests, flood the admin conduct queue, or
    # walk the whole player directory.
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        # The anonymous limit is deliberately high, and the reason matters: DRF keys it
        # on IP address, and **every server-rendered page shares one** — the Next.js
        # server calls the API on behalf of whoever is reading, so from Django's side a
        # thousand visitors look like one address. A tight anonymous limit would throttle
        # the site itself before it ever inconvenienced a scraper. It is a crude flood
        # guard, nothing more; the limits that do real work are the per-user scopes
        # below, which key on the account (Phase 11 step 4).
        #
        # Found the hard way: 60/min took the whole end-to-end suite down, because every
        # page render reads `/api/v1/config` and they all arrive from one host.
        "anon": env("THROTTLE_ANON", default="1200/min"),
        "user": env("THROTTLE_USER", default="600/min"),
        # The scopes below are the ones that *reach another person* — an inbox, a queue,
        # somebody's phone. They are deliberately much tighter, because there is no
        # legitimate reason to do any of them quickly.
        "reaching-people": env("THROTTLE_REACHING_PEOPLE", default="20/hour"),
        "reports": env("THROTTLE_REPORTS", default="10/hour"),
        "player-search": env("THROTTLE_PLAYER_SEARCH", default="120/hour"),
        "webhook": env("THROTTLE_WEBHOOK", default="600/min"),
    },
}

SPECTACULAR_SETTINGS = {
    "TITLE": "TurfApp API",
    "DESCRIPTION": (
        "Sports turf booking, matches, scoring and store API for Bangladesh. "
        "Authenticate with a Clerk session JWT: `Authorization: Bearer <token>`."
    ),
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # drf-spectacular's own views read this and ignore `permission_classes` passed to
    # `as_view()`, so this is the only place that decides who may read the schema.
    # The class itself checks `API_DOCS_PUBLIC` per request (Phase 11 step 4).
    "SERVE_PERMISSIONS": ["apps.core.permissions.CanReadApiDocs"],
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "COMPONENT_SPLIT_REQUEST": True,
    "SORT_OPERATIONS": False,
    # Several apps have a `status` field with different choices, and drf-spectacular
    # would otherwise mint names like `Status4eaEnum`. Naming them here keeps the
    # generated TypeScript readable and, more importantly, stable: an auto-resolved
    # name changes whenever another `status` field is added anywhere.
    "ENUM_NAME_OVERRIDES": {
        "BookingStatusEnum": "apps.bookings.models.BookingStatus.choices",
        "BookingModeEnum": "apps.bookings.models.BookingMode.choices",
        "BookingVisibilityEnum": "apps.bookings.models.BookingVisibility.choices",
        "PaymentStatusEnum": "apps.payments.models.PaymentStatus.choices",
        "PaymentMethodEnum": "apps.payments.models.PaymentMethod.choices",
        "TurfStatusEnum": "apps.turfs.models.TURF_STATUS_CHOICES",
        "TurfMembershipStatusEnum": "apps.turfs.models.TURF_MEMBERSHIP_STATUS_CHOICES",
        "TurfMembershipRoleEnum": "apps.turfs.models.TURF_MEMBERSHIP_ROLE_CHOICES",
        "GroundSurfaceEnum": "apps.turfs.models.GROUND_SURFACE_CHOICES",
        "SportProposalStatusEnum": "apps.sports.models.SPORT_PROPOSAL_STATUS_CHOICES",
        "StatValueTypeEnum": "apps.sports.models.STAT_VALUE_TYPE_CHOICES",
        "StatScopeEnum": "apps.sports.models.STAT_SCOPE_CHOICES",
        "PlayerGenderEnum": "apps.players.models.PLAYER_GENDER_CHOICES",
        "ProductKindEnum": "apps.inventory.models.PRODUCT_KIND_CHOICES",
        "ProductOwnerEnum": "apps.inventory.models.PRODUCT_OWNER_CHOICES",
        "StockLocationKindEnum": "apps.inventory.models.STOCK_LOCATION_KIND_CHOICES",
        "StockMovementTypeEnum": "apps.inventory.models.STOCK_MOVEMENT_TYPE_CHOICES",
        "CounterSaleStatusEnum": "apps.inventory.models.COUNTER_SALE_STATUS_CHOICES",
        "RentalStatusEnum": "apps.inventory.models.RENTAL_STATUS_CHOICES",
        "OrderStatusEnum": "apps.store.models.ORDER_STATUS_CHOICES",
        "OrderFulfilmentEnum": "apps.store.models.ORDER_FULFILMENT_CHOICES",
        "OrderPaymentMethodEnum": "apps.store.models.ORDER_PAYMENT_METHOD_CHOICES",
        "ActivitySourceEnum": "apps.fitness.models.ACTIVITY_SOURCE_CHOICES",
        "FitnessGoalTypeEnum": "apps.fitness.models.FITNESS_GOAL_TYPE_CHOICES",
        "BundleOccasionEnum": "apps.fitness.models.BUNDLE_OCCASION_CHOICES",
        "PaymentKindEnum": "apps.payments.models.PAYMENT_KIND_CHOICES",
        "RefundStatusEnum": "apps.payments.models.REFUND_STATUS_CHOICES",
        "LedgerAccountEnum": "apps.payments.models.LEDGER_ACCOUNT_CHOICES",
        "LedgerEntryTypeEnum": "apps.payments.models.LEDGER_ENTRY_TYPE_CHOICES",
        "PayoutStatusEnum": "apps.payments.models.PAYOUT_STATUS_CHOICES",
        "PlayerPreferredSideEnum": "apps.players.models.PLAYER_PREFERRED_SIDE_CHOICES",
        "NotificationKindEnum": "apps.notifications.models.NotificationKind.choices",
        "MatchStatusEnum": "apps.matches.models.MatchStatus.choices",
        "MatchVisibilityEnum": "apps.matches.models.MatchVisibility.choices",
        "JoinRequestStatusEnum": "apps.matches.models.JOIN_REQUEST_STATUS_CHOICES",
        "MatchInviteStatusEnum": "apps.matches.models.MATCH_INVITE_STATUS_CHOICES",
        "SquadInviteStatusEnum": "apps.matches.models.SQUAD_INVITE_STATUS_CHOICES",
        "SquadRoleEnum": "apps.matches.models.SQUAD_ROLE_CHOICES",
        "SquadMembershipStatusEnum": "apps.matches.models.SQUAD_MEMBERSHIP_STATUS_CHOICES",
        "MatchPlayerSourceEnum": "apps.matches.models.MATCH_PLAYER_SOURCE_CHOICES",
        "ScorecardStatusEnum": "apps.scoring.models.SCORECARD_STATUS_CHOICES",
        "MatchResultEnum": "apps.scoring.models.MATCH_RESULT_CHOICES",
        "TeamSideEnum": "apps.scoring.models.TEAM_SIDE_CHOICES",
    },
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env.list(
    "CORS_ALLOWED_ORIGINS", default=["http://localhost:3000", "http://127.0.0.1:3000"]
)
CORS_ALLOW_CREDENTIALS = True
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=CORS_ALLOWED_ORIGINS)

# ---------------------------------------------------------------------------
# Clerk
# ---------------------------------------------------------------------------
# Frontend API URL of the Clerk instance, e.g. https://<slug>.clerk.accounts.dev
# (dev) or https://clerk.<your-domain> (production). JWKS lives at
# <CLERK_FRONTEND_API_URL>/.well-known/jwks.json and `iss` must equal CLERK_ISSUER.
CLERK_FRONTEND_API_URL = env("CLERK_FRONTEND_API_URL", default="").rstrip("/")
CLERK_ISSUER = env("CLERK_ISSUER", default=CLERK_FRONTEND_API_URL).rstrip("/")
CLERK_SECRET_KEY = env("CLERK_SECRET_KEY", default="")
CLERK_WEBHOOK_SIGNING_SECRET = env("CLERK_WEBHOOK_SIGNING_SECRET", default="")
# `azp` allowlist. Clerk only sets the claim when the originating request carried an
# Origin header, so it is validated when present and skipped when absent.
CLERK_AUTHORIZED_PARTIES = env.list("CLERK_AUTHORIZED_PARTIES", default=CORS_ALLOWED_ORIGINS)
CLERK_JWKS_CACHE_SECONDS = env.int("CLERK_JWKS_CACHE_SECONDS", default=3600)
# Matches Clerk's own verifyToken default of 5s.
CLERK_JWT_LEEWAY_SECONDS = env.int("CLERK_JWT_LEEWAY_SECONDS", default=5)

# ---------------------------------------------------------------------------
# Business rules (configurable; never hard-code these inline)
# ---------------------------------------------------------------------------
# Booking confirmation (DECISIONS D3)
BOOKING_AUTO_CONFIRM_MIN_COMPLETED = 3
BOOKING_AUTO_CONFIRM_MIN_RELIABILITY = 80
BOOKING_CONFIRM_WINDOW_HOURS = 2
BOOKING_CONFIRM_CUTOFF_HOURS_BEFORE_START = 1
BOOKING_HORIZON_DAYS = 30
BOOKING_NO_SHOW_GRACE_MINUTES = 30

# Reliability score (DOMAIN §5)
RELIABILITY_STARTING_SCORE = 100
RELIABILITY_MAX = 100
RELIABILITY_NO_SHOW_DELTA = -15
RELIABILITY_LATE_CANCEL_DELTA = -5
RELIABILITY_COMPLETED_MATCH_DELTA = 2

# Scoring / ratings (DOMAIN §7–8, DECISIONS D7)
SCORECARD_AUTO_CONFIRM_HOURS = 24
MOTM_VOTE_WINDOW_HOURS = 24
# How many other players one person may rate after a match (DOMAIN §7's "up to N").
PEER_RATING_MAX_PER_MATCH = 10
SELF_ASSESSED_RATING_CAP = 75
RATING_PROVISIONAL_MATCHES = 10
RATING_VERIFIED_SCORECARD_WEIGHT = 1.5

# Fair play (DOMAIN §8). Only things that happened count: cards a scorer recorded on a
# locked card, and reports an admin upheld. An open report changes nothing.
FAIR_PLAY_YELLOW_PENALTY = 2
FAIR_PLAY_RED_PENALTY = 8
FAIR_PLAY_UPHELD_REPORT_PENALTY = 15
FAIR_PLAY_GOOD_THRESHOLD = 85
FAIR_PLAY_WARNING_THRESHOLD = 60

# Player search (DOMAIN §3). A deliberately small page: the ranking matters more than
# the length of the list.
PLAYER_SEARCH_PAGE_SIZE = 24
PLAYER_SEARCH_DEFAULT_RADIUS_KM = 10
LEADERBOARD_SIZE = 10
# Provisional overall = skills x SHARE + shared attributes x SHARE (must sum to 1).
# Phase 06's versioned engine replaces this blend.
OVERALL_SKILL_SHARE = 0.65
OVERALL_ATTRIBUTE_SHARE = 0.35
# Onboarding sliders start here, so a player who skips them is mid-range, not a 1.
ONBOARDING_DEFAULT_RATING = 50

# Store / delivery (DECISIONS D5)
TURF_DELIVERY_CUTOFF_HOURS = 16
# How close to kick-off an undelivered turf order becomes a warning for the admins.
STORE_DELIVERY_WARNING_HOURS = 4

# Fitness (DOMAIN §10).
# Bangladesh's weekend is Friday and Saturday, so a player's week runs Saturday to
# Friday — an ISO week would cut a Friday-night match off from the Saturday-morning one
# that belongs with it (DECISIONS D56). 5 = Saturday, matching `date.weekday()`.
FITNESS_WEEK_STARTS_ON = 5
#: Used when the player has not told us their weight; the log is flagged as an estimate.
FITNESS_FALLBACK_WEIGHT_KG = 70
#: How long before kick-off the hydration nudge goes out.
FITNESS_HYDRATION_LEAD_HOURS = 2
#: Default quiet hours, Dhaka time, when a player has not set their own.
FITNESS_QUIET_FROM = "22:00"
FITNESS_QUIET_UNTIL = "07:00"

# Payments (DOMAIN §5, §12; DECISIONS D8).
#: Default advance when a turf has not set one of its own. Zero keeps Phase 03's
#: cash-only behaviour until a turf opts in.
BOOKING_DEFAULT_ADVANCE_PERCENT = env.int("BOOKING_DEFAULT_ADVANCE_PERCENT", default=25)
#: What the platform takes when no commission plan says otherwise.
DEFAULT_BOOKING_COMMISSION_PERCENT = env("DEFAULT_BOOKING_COMMISSION_PERCENT", default="10.00")
DEFAULT_SALES_COMMISSION_PERCENT = env("DEFAULT_SALES_COMMISSION_PERCENT", default="5.00")

# SSLCommerz (DECISIONS D8). Sandbox by default; a store id is all that switches it on.
SSLCOMMERZ_STORE_ID = env("SSLCOMMERZ_STORE_ID", default="")
SSLCOMMERZ_STORE_PASSWORD = env("SSLCOMMERZ_STORE_PASSWORD", default="")
SSLCOMMERZ_SANDBOX = env.bool("SSLCOMMERZ_SANDBOX", default=True)
#: Development escape hatch: point the provider at a local stand-in so the payment path
#: can be exercised without sandbox credentials. Empty in every real environment.
SSLCOMMERZ_BASE_URL = env("SSLCOMMERZ_BASE_URL", default="")
#: Where the gateway sends the player back to. The IPN goes to the API instead.
PAYMENT_RETURN_BASE_URL = env("PAYMENT_RETURN_BASE_URL", default="http://localhost:3000")
#: The API's own public address, which is where a gateway posts its IPN. It has to be
#: reachable from the internet in production — localhost works only against a tunnel.
API_PUBLIC_BASE_URL = env("API_PUBLIC_BASE_URL", default="http://localhost:8000")

# Web push (DECISIONS D55). Unset in development and CI, where push is skipped.
VAPID_PUBLIC_KEY = env("VAPID_PUBLIC_KEY", default="")
VAPID_PRIVATE_KEY = env("VAPID_PRIVATE_KEY", default="")
VAPID_CONTACT_EMAIL = env("VAPID_CONTACT_EMAIL", default="admin@turfapp.local")

# Fitness (DOMAIN §10)
DEFAULT_PLAYER_WEIGHT_KG = 70

# ---------------------------------------------------------------------------
# Email / logging
# ---------------------------------------------------------------------------
# Django 6.1 deprecated the flat EMAIL_* settings in favour of MAILERS; the two cannot
# be mixed (ImproperlyConfigured), so notifications are built on MAILERS from the start.
MAILERS = {
    "default": {
        "BACKEND": env(
            "DJANGO_EMAIL_BACKEND",
            default="django.core.mail.backends.console.EmailBackend",
        ),
        "OPTIONS": {},
    }
}
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="TurfApp <no-reply@turfapp.local>")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{levelname} {asctime} {name} {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "root": {"handlers": ["console"], "level": env("DJANGO_LOG_LEVEL", default="INFO")},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}
