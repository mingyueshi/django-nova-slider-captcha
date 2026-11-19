import json

from django.core.management.base import BaseCommand

from nova_slider_captcha.rate_stats import METRICS, rate_stats

class Command(BaseCommand):
    help = "只读统计当前验证码限流状态和遗留桶。"

    def add_arguments(self, parser):
        parser.add_argument("--json", action="store_true", help="以标准 JSON 对象输出。")

    def handle(self, *args, **options):
        stats = rate_stats()
        if options["json"]:
            self.stdout.write(json.dumps(stats))
            return

        self.stdout.write(f"采样时间 {stats['sampled_at']}")
        self.stdout.write("action scope total debt cooldown prunable")
        for row in stats["states"]:
            self.stdout.write(" ".join(str(row[key]) for key in ("action", "scope", *METRICS)))
        legacy = stats["legacy"]
        self.stdout.write(f"遗留 RateBucket total={legacy['total']} prunable={legacy['prunable']}")
        self.stdout.write("债务与冷却可能重叠。有债务的桶仍可能有可用额度。")
        self.stdout.write("存量统计无法还原历史 429 响应。")
