"""URL configuration.

Everything the frontend talks to lives under ``/api/v1/``. The OpenAPI schema at
``/api/v1/schema/`` is what ``npm run gen:api`` generates frontend types from.

The schema and the two documentation UIs are **open in development and closed in
production** (``API_DOCS_PUBLIC``). A complete map of 167 endpoints, their payloads and
their parameters is the first thing anybody probing the API would want, and there is no
reason to hand it over — the people who need it have accounts.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django_otp.admin import OTPAdminSite
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)
from rest_framework.permissions import AllowAny, IsAdminUser

from apps.core.permissions import IsPlatformAdmin

#: Who may read the API documentation. `AllowAny` locally, so `npm run gen:api` and the
#: Swagger page work with no ceremony; platform admins only once it is deployed.
DOCS_PERMISSIONS = [AllowAny] if settings.API_DOCS_PUBLIC else [IsPlatformAdmin | IsAdminUser]

api_v1 = [
    path("", include("apps.core.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.sports.urls")),
    path("", include("apps.players.urls")),
    path("", include("apps.turfs.urls")),
    path("", include("apps.notifications.urls")),
    path("", include("apps.bookings.urls")),
    path("", include("apps.matches.urls")),
    path("", include("apps.scoring.urls")),
    path("", include("apps.ratings.urls")),
    path("", include("apps.inventory.urls")),
    path("", include("apps.store.urls")),
    path("", include("apps.fitness.urls")),
    path("", include("apps.payments.urls")),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    # url_name must carry the namespace: these URLs live under the "v1" instance namespace.
    path("docs/", SpectacularSwaggerView.as_view(url_name="v1:schema"), name="swagger-ui"),
    path("redoc/", SpectacularRedocView.as_view(url_name="v1:schema"), name="redoc"),
]

# A password alone is not enough to reach every row in the database.
#
# Clerk guards player and owner accounts and brings its own second factor, but the Django
# admin is a separate door with a separate password — and behind it is every booking,
# every payment and every player's details. `OTPAdminSite` refuses a login that has not
# also verified a TOTP device, which an admin registers under "TOTP devices"
# (DECISIONS D64). Off in development, where there is nothing worth protecting and a
# second factor is only friction.
if settings.ADMIN_REQUIRES_OTP:
    admin.site.__class__ = OTPAdminSite

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1, "api"), namespace="v1")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
