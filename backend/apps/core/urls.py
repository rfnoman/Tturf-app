from django.urls import path

from .views import ClientConfigView, HealthView

urlpatterns = [
    path("health", HealthView.as_view(), name="health"),
    path("config", ClientConfigView.as_view(), name="client-config"),
]
