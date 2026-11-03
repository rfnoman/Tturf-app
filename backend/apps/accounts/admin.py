from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin
from django.utils.translation import gettext_lazy as _

from .models import User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    """Support-oriented admin. Accounts are created by Clerk, so editing is limited."""

    list_display = (
        "clerk_id",
        "email",
        "full_name",
        "is_platform_admin",
        "is_active",
        "created_at",
    )
    list_filter = ("is_platform_admin", "is_active", "is_staff", "is_superuser")
    search_fields = ("clerk_id", "email", "phone", "first_name", "last_name")
    ordering = ("-created_at",)
    readonly_fields = ("id", "clerk_id", "created_at", "updated_at", "last_synced_at", "last_login")

    fieldsets = (
        (None, {"fields": ("id", "clerk_id", "password")}),
        (
            _("Personal info"),
            {"fields": ("first_name", "last_name", "email", "phone", "image_url")},
        ),
        (
            _("Permissions"),
            {
                "fields": (
                    "is_active",
                    "is_platform_admin",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (_("Dates"), {"fields": ("last_login", "last_synced_at", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("clerk_id", "email", "password1", "password2"),
            },
        ),
    )
