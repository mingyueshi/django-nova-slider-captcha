import uuid

from django.db import models


class Challenge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session_hash = models.CharField(max_length=64, db_index=True)
    purpose = models.CharField(max_length=32)
    target_x = models.PositiveSmallIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    # Literal legacy defaults are deliberate: migrations and old rows must not
    # inherit a later host configuration. services.issue writes current policy.
    max_attempts = models.PositiveSmallIntegerField(default=5)
    tolerance = models.PositiveSmallIntegerField(default=4)
    solved = models.BooleanField(default=False)
    token_hash = models.CharField(max_length=64, null=True, unique=True)
    token_expires_at = models.DateTimeField(null=True)
    token_consumed = models.BooleanField(default=False)


class RateBucket(models.Model):
    """Legacy upgrade/cleanup only. Removal requires a separate migration."""
    key = models.CharField(max_length=128, primary_key=True)
    count = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)


class RateLimitState(models.Model):
    """Stable-key GCRA debt, kept separate from the legacy fixed windows."""

    key = models.CharField(max_length=128, primary_key=True)
    tat_us = models.PositiveBigIntegerField(default=0, db_index=True)
    blocked_until_us = models.PositiveBigIntegerField(default=0, db_index=True)
