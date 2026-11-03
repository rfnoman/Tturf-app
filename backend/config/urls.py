"""URL configuration.

Everything the frontend talks to lives under ``/api/v1/``. The OpenAPI schema at
``/api/v1/schema/`` is what ``npm run gen:api`` generates frontend types from.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

api_v1 = [
    path("", include("apps.core.urls")),
    path("", include("apps.accounts.urls")),
    path("", include("apps.sports.urls")),
    path("", include("apps.players.urls")),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    # url_name must carry the namespace: these URLs live under the "v1" instance namespace.
    path("docs/", SpectacularSwaggerView.as_view(url_name="v1:schema"), name="swagger-ui"),
    path("redoc/", SpectacularRedocView.as_view(url_name="v1:schema"), name="redoc"),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1, "api"), namespace="v1")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
