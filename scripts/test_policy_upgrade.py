"""Real 0002 -> 0003 upgrade in a private database; never touch demo data."""
import os
from pathlib import Path
import secrets
import tempfile
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
from django.conf import settings

with tempfile.TemporaryDirectory(prefix="nova-slider-policy-upgrade-") as directory:
    settings.DATABASES["default"]["NAME"] = str(Path(directory) / "migration.sqlite3")
    settings.NOVA_SLIDER_MAX_ATTEMPTS = 20
    settings.NOVA_SLIDER_TOLERANCE = 10
    settings.NOVA_SLIDER_CHALLENGE_TTL = 600
    import django
    django.setup()
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor
    from django.utils import timezone
    from nova_slider_captcha import services

    app = "nova_slider_captcha"
    previous = [(app, "0002_ratelimitstate")]
    current = [(app, "0003_challenge_policy")]
    executor = MigrationExecutor(connection)
    executor.migrate(previous)
    old = executor.loader.project_state(previous).apps.get_model(app, "Challenge")
    now = timezone.now()
    request = SimpleNamespace(session={"_nova_slider_binding": "migration-session"}, META={})
    binding = services.session_binding(request)
    token = secrets.token_urlsafe(32)
    live = old.objects.create(session_hash=binding, purpose="demo", target_x=100, attempts=4, expires_at=now + timedelta(seconds=120))
    exhausted = old.objects.create(session_hash=binding, purpose="demo", target_x=100, attempts=5, expires_at=now + timedelta(seconds=120))
    proof = old.objects.create(session_hash=binding, purpose="demo", target_x=100, attempts=1, solved=True,
                               expires_at=now + timedelta(seconds=120), token_hash=services._hash(token, "token"),
                               token_expires_at=now + timedelta(seconds=60))
    before = {row["id"]: row for row in old.objects.values()}
    MigrationExecutor(connection).migrate(current)
    from nova_slider_captcha.models import Challenge
    for row in Challenge.objects.values():
        self_snapshot = (row.pop("max_attempts"), row.pop("tolerance"))
        assert self_snapshot == (5, 4), self_snapshot
        assert row == before[row["id"]], "Existing challenge/proof data changed"
    with patch("nova_slider_captcha.services.timezone.now", return_value=now):
        # Current permissive settings must not expand a legacy row's policy.
        result = services.verify(request, live.pk, 105)
        assert result["code"] == "incorrect" and result["attemptsRemaining"] == 0
        assert services.verify(request, live.pk, 100)["code"] == "attempts_exhausted"
        assert services.verify(request, exhausted.pk, 100)["code"] == "attempts_exhausted"
        assert services.consume(token, request, "demo")
        assert not services.consume(token, request, "demo")
        issued = services.issue(request, "demo")
    row = Challenge.objects.get(pk=issued["challengeId"])
    assert (row.max_attempts, row.tolerance) == (20, 10)
    assert row.expires_at == now + timedelta(seconds=600)
    connection.close()
    print("Challenge policy upgrade preserves legacy 5/4 and proof state")
