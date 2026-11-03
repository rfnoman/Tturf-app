from django.urls import path

from .views import ClerkWebhookView, MeView

urlpatterns = [
    path("me", MeView.as_view(), name="me"),
    path("webhooks/clerk", ClerkWebhookView.as_view(), name="clerk-webhook"),
]
