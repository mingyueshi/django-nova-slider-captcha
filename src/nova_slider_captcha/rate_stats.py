"""Read-only aggregate snapshots for operational tools."""
from django.db import router
from django.db.models import Case, Count, Q, Value, When
from django.db.models.functions import Length
from django.utils.timezone import now as current_time

from .conf import RATE_DEFAULTS
from .models import RateBucket, RateLimitState
from .services import timestamp_us

GROUPS = tuple(tuple(key.split("_", 1)) for key in RATE_DEFAULTS)
METRICS = ("total", "debt", "cooldown", "prunable")


def rate_stats():
    now = current_time()
    now_us = timestamp_us(now)
    prefixes = [f"{action}:{scope}:" for action, scope in GROUPS]
    group = Case(
        *(When(key__regex=f"^{prefix}[0-9a-f]{{64}}$", key_length=len(prefix) + 64, then=Value(index))
          for index, prefix in enumerate(prefixes)),
        default=Value(len(GROUPS)),
    )
    states = (
        RateLimitState.objects.using(router.db_for_write(RateLimitState))
        .alias(key_length=Length("key")).annotate(bucket_group=group)
        .values("bucket_group")
        .annotate(
            total=Count("pk"),
            debt=Count("pk", filter=Q(tat_us__gt=now_us)),
            cooldown=Count("pk", filter=Q(blocked_until_us__gt=now_us)),
            prunable=Count("pk", filter=Q(tat_us__lte=now_us, blocked_until_us__lte=now_us)),
        )
    )
    counts = {row["bucket_group"]: {metric: row[metric] for metric in METRICS} for row in states}
    groups = [
        {"action": action, "scope": scope, **counts.get(index, dict.fromkeys(METRICS, 0))}
        for index, (action, scope) in enumerate((*GROUPS, ("other", "other")))
    ]
    legacy = RateBucket.objects.using(router.db_for_write(RateBucket)).aggregate(
        total=Count("pk"), prunable=Count("pk", filter=Q(expires_at__lt=now)),
    )
    return {"sampled_at": now.isoformat(), "states": groups, "legacy": legacy}
