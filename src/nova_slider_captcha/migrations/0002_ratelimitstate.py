"""Preserve live legacy quota conservatively while moving to stable-key GCRA.

Drain old-version writes before applying this migration and starting new code.
An active legacy scope pauses until its latest expiry (normally <=120 seconds).
Never silently drop the new debt on downgrade: automatic reversal is refused.
A deliberate code rollback requires traffic drain, debt/legacy expiry clearance,
and keeping both tables until an operator has planned the schema transition.
"""
from datetime import datetime, timezone as datetime_timezone

from django.db import migrations, models
from django.db.migrations.exceptions import IrreversibleError
from django.utils import timezone


def preserve_active_legacy_limits(apps, schema_editor):
    legacy = apps.get_model("nova_slider_captcha", "RateBucket")
    state = apps.get_model("nova_slider_captcha", "RateLimitState")
    database = schema_editor.connection.alias
    epoch = datetime(1970, 1, 1, tzinfo=datetime_timezone.utc)
    for bucket in legacy.objects.using(database).filter(expires_at__gt=timezone.now()).iterator(chunk_size=512):
        parts = bucket.key.split(":")
        if (len(parts) != 4 or parts[0] not in ("issue", "verify") or parts[1] not in ("ip", "session")
                or not parts[2].isdigit() or len(parts[3]) != 64
                or any(c not in "0123456789abcdef" for c in parts[3])):
            continue
        key = f"{parts[0]}:{parts[1]}:{parts[3]}"
        expires_at = bucket.expires_at
        if timezone.is_naive(expires_at):
            expires_at = timezone.make_aware(expires_at, timezone.get_default_timezone())
        delta = expires_at - epoch
        expiry_us = (delta.days * 86_400 + delta.seconds) * 1_000_000 + delta.microseconds
        state.objects.using(database).get_or_create(key=key)
        state.objects.using(database).filter(key=key, blocked_until_us__lt=expiry_us).update(blocked_until_us=expiry_us)


def refuse_debt_loss(apps, schema_editor):
    raise IrreversibleError(
        "GCRA state cannot be automatically discarded without resetting live quota. "
        "Drain traffic, wait for all quota debt and legacy expiries (normally at least "
        "120 seconds), and plan a code/schema rollback while preserving both tables."
    )


class Migration(migrations.Migration):
    dependencies = [("nova_slider_captcha", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="RateLimitState",
            fields=[
                ("key", models.CharField(max_length=128, primary_key=True, serialize=False)),
                ("tat_us", models.PositiveBigIntegerField(db_index=True, default=0)),
                ("blocked_until_us", models.PositiveBigIntegerField(db_index=True, default=0)),
            ],
        ),
        migrations.RunPython(preserve_active_legacy_limits, refuse_debt_loss),
    ]
