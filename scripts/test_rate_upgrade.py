"""Isolated real migration/rollback regression, used by the Django test suite."""
import os
import sys
from pathlib import Path
import tempfile
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

# Import repository settings without relying on the caller's PYTHONPATH.
# Do not add src: installed-wheel checks must keep using the installed package.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
from django.conf import settings

with tempfile.TemporaryDirectory(prefix="nova-slider-upgrade-") as directory:
    settings.DATABASES["default"]["NAME"] = str(Path(directory) / "migration.sqlite3")
    if "--naive-time" in sys.argv:
        settings.USE_TZ = False
    import django
    django.setup()
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    from django.db.migrations.exceptions import IrreversibleError
    from django.utils import timezone
    from nova_slider_captcha import services

    app = "nova_slider_captcha"
    old_target = [(app, "0001_initial")]
    new_target = [(app, "0002_ratelimitstate")]
    executor = MigrationExecutor(connection)
    executor.migrate(old_target)
    old_apps = executor.loader.project_state(old_target).apps
    old_bucket = old_apps.get_model(app, "RateBucket")
    old_challenge = old_apps.get_model(app, "Challenge")
    now = timezone.now()
    ip_hash = services._hash("192.0.2.1", "ip")
    window = int(now.timestamp()) // 60
    old_bucket.objects.create(key=f"issue:ip:{window}:{ip_hash}", count=60, expires_at=now + timedelta(seconds=30))
    old_bucket.objects.create(key=f"issue:ip:{window+1}:{ip_hash}", count=60, expires_at=now + timedelta(seconds=80, microseconds=1))
    old_bucket.objects.create(key=f"verify:ip:{window}:{ip_hash}", count=120, expires_at=now - timedelta(microseconds=1))
    old_bucket.objects.create(key="not-a-runtime-key", count=1, expires_at=now + timedelta(seconds=99))
    proof = old_challenge.objects.create(session_hash="unchanged", purpose="login", target_x=70,
        solved=True, attempts=1, expires_at=now + timedelta(seconds=120),
        token_hash="a" * 64, token_expires_at=now + timedelta(seconds=60), token_consumed=False)
    before = old_challenge.objects.get(pk=proof.pk).__dict__.copy()
    before.pop("_state")
    executor = MigrationExecutor(connection)
    executor.migrate(new_target)
    # This regression intentionally stops at 0002. Use its historical Challenge
    # schema rather than the current model (which may have later snapshot fields).
    Challenge = executor.loader.project_state(new_target).apps.get_model(app, "Challenge")
    from nova_slider_captcha.models import RateBucket, RateLimitState
    migrated = RateLimitState.objects.get()
    assert migrated.key == f"issue:ip:{ip_hash}"
    assert migrated.tat_us == 0
    assert migrated.blocked_until_us == services.timestamp_us(now + timedelta(seconds=80, microseconds=1))
    assert RateBucket.objects.count() == 4
    after = Challenge.objects.get(pk=proof.pk).__dict__.copy()
    after.pop("_state")
    assert before == after, "Challenge/proof state changed during quota migration"
    request = SimpleNamespace(session={"_nova_slider_binding": "new-session"}, META={"REMOTE_ADDR": "192.0.2.1"})
    with patch("nova_slider_captcha.services.timezone.now", return_value=now):
        denied = services.allow_request(request, "issue")
        assert not denied and denied.retry_after == 81
    with patch("nova_slider_captcha.services.timezone.now", return_value=now + timedelta(seconds=80, microseconds=1)):
        assert services.allow_request(request, "issue")
    debt = list(RateLimitState.objects.order_by("key").values())
    try:
        MigrationExecutor(connection).migrate(old_target)
    except IrreversibleError as error:
        assert "Drain traffic" in str(error)
    else:
        raise AssertionError("Unsafe migration reversal unexpectedly discarded quota debt")
    assert debt == list(RateLimitState.objects.order_by("key").values())
    assert (app, "0002_ratelimitstate") in MigrationExecutor(connection).loader.applied_migrations
    connection.close()
    print("Legacy upgrade and rollback guard passed")
