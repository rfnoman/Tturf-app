import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command

pytestmark = pytest.mark.django_db


def test_seed_demo_is_idempotent():
    call_command("seed_demo", verbosity=0)
    call_command("seed_demo", verbosity=0)

    User = get_user_model()
    admins = User.objects.filter(clerk_id="seed_platform_admin")
    assert admins.count() == 1
    assert admins.get().is_platform_admin
