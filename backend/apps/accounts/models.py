"""The user account.

Authentication lives in Clerk; Django holds a mirror of the account keyed by
``clerk_id`` (Clerk's ``user_...`` id, the ``sub`` claim of a session token). Roles are
permissions on one account, never separate user types (DOMAIN §1): ``is_platform_admin``
here, turf owner/staff via ``TurfMembership`` (Phase 02), rider via an assignment
(Phase 08).
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils.translation import gettext_lazy as _

from apps.core.models import BaseModel


class UserManager(BaseUserManager):
    """Users are normally created by Clerk sync, not by hand."""

    use_in_migrations = True

    def create_user(self, clerk_id: str, email: str = "", password: str | None = None, **extra):
        if not clerk_id:
            raise ValueError("clerk_id is required")
        user = self.model(clerk_id=clerk_id, email=self.normalize_email(email), **extra)
        # Clerk owns credentials; an unusable password is the norm here.
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(
        self, clerk_id: str, email: str = "", password: str | None = None, **extra
    ):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("is_platform_admin", True)
        if not extra["is_staff"] or not extra["is_superuser"]:
            raise ValueError("Superuser must have is_staff and is_superuser set.")
        return self.create_user(clerk_id, email, password, **extra)


class User(BaseModel, AbstractBaseUser, PermissionsMixin):
    clerk_id = models.CharField(
        _("Clerk user id"),
        max_length=255,
        unique=True,
        db_index=True,
        help_text="Clerk's user id; the `sub` claim of a session token.",
    )
    email = models.EmailField(_("email address"), blank=True, db_index=True)
    phone = models.CharField(
        _("phone number"),
        max_length=32,
        blank=True,
        help_text="E.164, e.g. +8801XXXXXXXXX. Unverified in v1 (DECISIONS D9).",
    )
    first_name = models.CharField(_("first name"), max_length=150, blank=True)
    last_name = models.CharField(_("last name"), max_length=150, blank=True)
    image_url = models.URLField(_("avatar URL"), max_length=500, blank=True)

    is_platform_admin = models.BooleanField(
        _("platform admin"),
        default=False,
        help_text="Approves turfs and sports, handles disputes and conduct reports.",
    )
    is_active = models.BooleanField(
        _("active"),
        default=True,
        help_text="Set to False instead of deleting (Clerk `user.deleted` soft-deactivates).",
    )
    is_staff = models.BooleanField(
        _("django admin access"),
        default=False,
        help_text="Access to the Django admin site. Unrelated to turf staff.",
    )
    last_synced_at = models.DateTimeField(
        _("last synced from Clerk"), null=True, blank=True, editable=False
    )

    objects = UserManager()

    USERNAME_FIELD = "clerk_id"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = _("user")
        verbose_name_plural = _("users")
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.full_name or self.email or self.clerk_id

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def get_full_name(self) -> str:
        return self.full_name

    def get_short_name(self) -> str:
        return self.first_name or self.full_name or self.email
