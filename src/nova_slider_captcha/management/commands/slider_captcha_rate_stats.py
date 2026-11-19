import json

from django.core.management.base import BaseCommand
from django.db import router
from django.db.models import Case, Count, Q, Value, When
from django.db.models.functions import Length
from django.utils import timezone

from nova_slider_captcha.conf import RATE_DEFAULTS
from nova_slider_captcha.models import RateBucket, RateLimitState
from nova_slider_captcha.services import timestamp_us

GROUPS = tuple(tuple(key.split("_", 1)) for key in RATE_DEFAULTS)
METRICS = ("total", "debt", "cooldown", "prunable")


class Command(BaseCommand):
    help = "只读统计当前验证码限流状态和遗留桶。"

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="以标准 JSON 对象输出。")

    def handle(self, *args, **options):
        now = timezone.now()
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
        if options["json"]:
            self.stdout.write(json.dumps({"sampled_at": now.isoformat(), "states": groups, "legacy": legacy}))
            return

        self.stdout.write(f"采样时间 {now.isoformat()}")
        self.stdout.write("action scope total debt cooldown prunable")
        for row in groups:
            self.stdout.write(" ".join(str(row[key]) for key in ("action", "scope", *METRICS)))
        self.stdout.write(f"遗留 RateBucket total={legacy['total']} prunable={legacy['prunable']}")
        self.stdout.write("债务与冷却可能重叠。有债务的桶仍可能有可用额度。")
        self.stdout.write("存量统计无法还原历史 429 响应。")
