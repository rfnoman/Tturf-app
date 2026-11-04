"""Platform settings: the only place the business can move a rule without a deploy."""

from django.contrib import admin, messages
from django.core.cache import cache

from .models import PlatformSetting
from .utils import setting


@admin.register(PlatformSetting)
class PlatformSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "value", "code_default", "description", "updated_at")
    search_fields = ("key", "description")
    readonly_fields = ("code_default", "updated_by", "created_at", "updated_at")

    @admin.display(description="Default in code")
    def code_default(self, obj) -> str:
        """What the rule would be with this row deleted.

        Shown because the override direction is the whole design: deleting a row
        restores the code's value, and an admin about to change a number should be able
        to see what they are overriding.
        """
        from django.conf import settings as django_settings

        value = getattr(django_settings, obj.key, None)
        return "—" if value is None else str(value)

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

        # The cache is what makes this cheap to read; it is also what would make a change
        # take a minute to appear, which is confusing for somebody who just pressed save.
        cache.delete(f"platform-setting:{obj.key}")

        messages.info(request, f"{obj.key} is now {setting(obj.key)!r}, effective immediately.")

    def delete_model(self, request, obj):
        key = obj.key
        super().delete_model(request, obj)
        cache.delete(f"platform-setting:{key}")
        messages.info(request, f"{key} is back to its default in code.")
