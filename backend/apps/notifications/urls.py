from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views import NotificationViewSet

router = SimpleRouter(trailing_slash=False)
router.register("me/notifications", NotificationViewSet, basename="my-notification")

urlpatterns = [path("", include(router.urls))]
