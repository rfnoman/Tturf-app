from django.urls import path

from .views import (
    ActivityView,
    BundleAddView,
    BundleListView,
    DashboardView,
    GoalView,
    NotificationStreamView,
    PushSubscribeView,
    ReminderPreferenceView,
    WeekView,
)

urlpatterns = [
    path("me/dashboard", DashboardView.as_view(), name="fitness-dashboard"),
    path("me/activity", ActivityView.as_view(), name="activity"),
    path("me/activity/week", WeekView.as_view(), name="activity-week"),
    path("me/goals", GoalView.as_view(), name="goals"),
    path("me/reminders", ReminderPreferenceView.as_view(), name="reminders"),
    path("me/push", PushSubscribeView.as_view(), name="push"),
    path("me/notifications/stream", NotificationStreamView.as_view(), name="notification-stream"),
    path("bundles", BundleListView.as_view(), name="bundles"),
    path("bundles/<slug:slug>/add", BundleAddView.as_view(), name="bundle-add"),
]
