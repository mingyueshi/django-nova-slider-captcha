import io
import json
from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.db import connections
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from nova_slider_captcha.models import RateBucket, RateLimitState
from nova_slider_captcha.services import timestamp_us
from tests.test_boundaries import CaptchaReplicaRouter


@override_settings(DATABASE_ROUTERS=[CaptchaReplicaRouter()])
class RateStatsTests(TestCase):
    databases = {"default", "captcha", "replica"}

    def run_stats(self, now, *, as_json):
        output = io.StringIO()
        with (
            patch("nova_slider_captcha.management.commands.slider_captcha_rate_stats.timezone.now",
                  return_value=now) as clock,
            CaptureQueriesContext(connections["captcha"]) as writer,
            CaptureQueriesContext(connections["replica"]) as replica,
            CaptureQueriesContext(connections["default"]) as default,
        ):
            call_command("slider_captcha_rate_stats", stdout=output, json=as_json)
        clock.assert_called_once_with()
        self.assertEqual(len(writer), 2)
        self.assertTrue(all(query["sql"].lstrip().upper().startswith("SELECT ") for query in writer))
        self.assertEqual(len(replica), 0)
        self.assertEqual(len(default), 0)
        return output.getvalue()

    def test_empty_database_has_stable_zero_groups(self):
        now = timezone.now()
        result = json.loads(self.run_stats(now, as_json=True))
        self.assertEqual(result["sampled_at"], now.isoformat())
        self.assertEqual(result["legacy"], {"total": 0, "prunable": 0})
        self.assertEqual([(row["action"], row["scope"]) for row in result["states"]],
                         [("init", "ip"), ("issue", "session"), ("issue", "ip"),
                          ("verify", "session"), ("verify", "ip"), ("other", "other")])
        for row in result["states"]:
            self.assertEqual([row[key] for key in ("total", "debt", "cooldown", "prunable")], [0] * 4)

    def test_boundaries_overlap_privacy_and_format_agreement(self):
        now = timezone.now()
        current = timestamp_us(now)
        buckets = RateLimitState.objects.using("captcha")
        for subject, debt, cooldown in (("a", 0, 0), ("b", 1, 0), ("c", 0, 1), ("d", 1, 1)):
            buckets.create(key="issue:ip:" + subject * 64, tat_us=current + debt,
                           blocked_until_us=current + cooldown)
        private_keys = ["unknown:ip:" + "e" * 64, "issue:ip:malformed-private", "legacy-private"]
        for key in private_keys[:2]:
            buckets.create(key=key, tat_us=current, blocked_until_us=current)
        RateLimitState.objects.using("replica").create(key="verify:ip:" + "f" * 64)
        for offset in (-1, 0, 1):
            RateBucket.objects.using("captcha").create(
                key=f"{private_keys[2]}-{offset}", expires_at=now + timedelta(microseconds=offset),
            )

        raw = self.run_stats(now, as_json=True)
        plain = self.run_stats(now, as_json=False)
        result = json.loads(raw)
        self.assertEqual(result["states"][2],
                         {"action": "issue", "scope": "ip", "total": 4, "debt": 2, "cooldown": 2, "prunable": 1})
        self.assertEqual(result["states"][-1],
                         {"action": "other", "scope": "other", "total": 2, "debt": 0, "cooldown": 0, "prunable": 2})
        self.assertEqual(sum(row["total"] for row in result["states"]), 6)
        self.assertEqual(result["legacy"], {"total": 3, "prunable": 1})
        for row in result["states"]:
            self.assertIn(" ".join(str(row[k]) for k in ("action", "scope", "total", "debt", "cooldown", "prunable")),
                          plain.splitlines())
        self.assertIn("遗留 RateBucket total=3 prunable=1", plain.splitlines())
        self.assertIn("债务与冷却可能重叠", plain)
        self.assertIn("存量统计无法还原历史 429", plain)
        for private in (*private_keys, "a" * 64, "b" * 64, "c" * 64, "d" * 64):
            self.assertNotIn(private, raw + plain)
