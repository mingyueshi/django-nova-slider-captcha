"""Exact-clock quota regressions; no sleeping or minute-boundary flakiness."""
import io
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timedelta, timezone as datetime_timezone
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.db import DatabaseError, connection
from django.db.models.signals import post_delete
from django.test import SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from nova_slider_captcha import services
from nova_slider_captcha.checks import captcha_settings_check
from nova_slider_captcha.conf import MAX_RATE_LIMIT, RATE_PERIOD_US, rate_limit
from nova_slider_captcha.models import Challenge, RateBucket, RateLimitState
from tests.test_captcha import CaptchaHelpers

EPOCH = datetime(1970, 1, 1, tzinfo=datetime_timezone.utc)


def request(nonce="session-a", ip="192.0.2.1"):
    return SimpleNamespace(session={"_nova_slider_binding": nonce}, META={"REMOTE_ADDR": ip})


def at(us):
    return patch("nova_slider_captcha.services.timezone.now", return_value=EPOCH + timedelta(microseconds=us))


def scope_key(action="issue", scope="ip", subject="192.0.2.1"):
    return f"{action}:{scope}:{services._hash(subject, 'ip' if scope == 'ip' else 'binding')}"


@override_settings(NOVA_SLIDER_RATE_LIMITS={"issue_ip": 3, "issue_session": 3})
class GCRATests(CaptchaHelpers, TestCase):
    def test_existing_accepted_scopes_use_only_two_conditional_updates(self):
        with at(1_000_000):
            self.assertTrue(services.allow_request(request(), "issue"))
            with CaptureQueriesContext(connection) as queries:
                self.assertTrue(services.allow_request(request(), "issue"))
        self.assertEqual(len(queries), 2)
        self.assertTrue(all(query["sql"].startswith("UPDATE ") for query in queries))
        self.assertTrue(all('"blocked_until_us" <=' in query["sql"] for query in queries))

    def test_creation_charges_first_request_without_another_update(self):
        with at(1_000_000), CaptureQueriesContext(connection) as queries:
            self.assertTrue(services.allow_request(request(), "issue"))
        self.assertEqual(sum(query["sql"].startswith("UPDATE ") for query in queries), 2)
        self.assertEqual(sum(query["sql"].startswith("INSERT ") for query in queries), 2)
        self.assertEqual(set(RateLimitState.objects.values_list("tat_us", flat=True)), {21_000_000})

    def test_concurrent_creator_cooldown_is_never_overwritten(self):
        now = 1_000_000
        def competitor(**kwargs):
            state = RateLimitState.objects.create(key=kwargs["key"], tat_us=now + RATE_PERIOD_US, blocked_until_us=now + 10_000_000)
            return state, False
        with at(now), patch.object(RateLimitState.objects, "get_or_create", side_effect=competitor):
            self.assertFalse(services.allow_request(request(), "issue"))
        state = RateLimitState.objects.get(pk=scope_key())
        self.assertEqual((state.tat_us, state.blocked_until_us), (now + RATE_PERIOD_US, now + 10_000_000))
        self.assertEqual(RateLimitState.objects.count(), 1)

    def test_disappearance_between_creation_lookup_and_retry_fails_closed(self):
        def disappears(**kwargs):
            state = RateLimitState.objects.create(key=kwargs["key"])
            state.delete()  # A fully idle row can be removed by quota cleanup.
            return state, False
        with at(1_000_000), patch.object(RateLimitState.objects, "get_or_create", side_effect=disappears):
            decision = services.allow_request(request(), "issue")
        self.assertFalse(decision)
        self.assertEqual(decision.retry_after, 1)
        self.assertFalse(RateLimitState.objects.exists())

    def test_negative_clock_does_not_charge_new_denied_state(self):
        with at(-1):
            self.assertFalse(services.allow_request(request(), "issue"))
        self.assertEqual(RateLimitState.objects.get(pk=scope_key()).tat_us, 0)

    def test_shared_cross_backend_contract_fixture(self):
        fixture = json.loads((Path(__file__).parent / "fixtures/gcra.json").read_text())
        self.assertEqual(fixture["periodUs"], RATE_PERIOD_US)
        self.assertEqual(fixture["capacity"], rate_limit("issue", "ip"))
        for step in fixture["steps"]:
            with self.subTest(step=step), at(step["nowUs"]):
                decision = services.allow_request(request(), "issue")
                self.assertEqual(bool(decision), step["allowed"])
                self.assertEqual(decision.retry_after, step["retryAfter"])
                self.assertEqual(RateLimitState.objects.get(pk=scope_key()).tat_us, step["tatUs"])

    def test_initial_capacity_and_exact_microsecond_refill(self):
        start = 1_800_000_000_000_001
        with at(start):
            self.assertEqual([bool(services.allow_request(request(), "issue")) for _ in range(4)], [True, True, True, False])
        with at(start + 19_999_999):
            denied = services.allow_request(request(), "issue")
            self.assertFalse(denied)
            self.assertEqual(denied.retry_after, 1)
        with at(start + 20_000_000):
            self.assertTrue(services.allow_request(request(), "issue"))
            self.assertFalse(services.allow_request(request(), "issue"))
        self.assertEqual(RateLimitState.objects.get(pk=scope_key()).tat_us, start + 80_000_000)

    def test_wall_clock_minute_boundary_does_not_double_capacity(self):
        with at(59_999_999):
            self.assertTrue(all(services.allow_request(request(), "issue") for _ in range(3)))
        with at(60_000_001):
            self.assertFalse(any(services.allow_request(request(), "issue") for _ in range(3)))
        self.assertEqual(RateLimitState.objects.count(), 2)
        self.assertFalse(RateBucket.objects.exists())

    @override_settings(NOVA_SLIDER_RATE_LIMITS={"issue_ip": 7, "issue_session": 7})
    def test_fractional_refill_interval_rounds_up(self):
        interval = (RATE_PERIOD_US + 6) // 7
        with at(1_000_001):
            self.assertTrue(all(services.allow_request(request(), "issue") for _ in range(7)))
        with at(1_000_001 + interval - 1):
            self.assertFalse(services.allow_request(request(), "issue"))
        with at(1_000_001 + interval):
            self.assertTrue(services.allow_request(request(), "issue"))

    def test_denials_do_not_change_tat_or_upgrade_block(self):
        with at(1_000_000):
            for _ in range(3):
                services.allow_request(request(), "issue")
            before = list(RateLimitState.objects.order_by("key").values())
            for _ in range(8):
                self.assertFalse(services.allow_request(request(), "issue"))
            self.assertEqual(before, list(RateLimitState.objects.order_by("key").values()))

    def test_backward_clock_does_not_reset_quota(self):
        with at(120_000_000):
            for _ in range(3):
                services.allow_request(request(), "issue")
        with at(60_000_000):
            denied = services.allow_request(request(), "issue")
            self.assertFalse(denied)
            self.assertEqual(denied.retry_after, 80)
        with at(139_999_999):
            self.assertFalse(services.allow_request(request(), "issue"))
        with at(140_000_000):
            self.assertTrue(services.allow_request(request(), "issue"))

    def test_idle_refill_restores_capacity_not_unbounded_credit(self):
        with at(1_000_000):
            services.allow_request(request(), "issue")
        with at(10_000_000_000):
            self.assertEqual(sum(bool(services.allow_request(request(), "issue")) for _ in range(6)), 3)

    def test_ip_quota_survives_new_sessions_and_rejected_ip_creates_no_session_rows(self):
        with at(1_000_000):
            for n in range(3):
                self.assertTrue(services.allow_request(request(nonce=f"new-{n}"), "issue"))
            self.assertFalse(services.allow_request(request(nonce="new-4"), "issue"))
        self.assertEqual(RateLimitState.objects.count(), 4)
        self.assertFalse(RateLimitState.objects.filter(pk=scope_key(scope="session", subject="new-4")).exists())

    @override_settings(NOVA_SLIDER_RATE_LIMITS={"issue_ip": 10, "issue_session": 1})
    def test_session_quota_survives_ip_change_and_other_session_is_independent(self):
        with at(1_000_000):
            self.assertTrue(services.allow_request(request(), "issue"))
            self.assertFalse(services.allow_request(request(ip="192.0.2.2"), "issue"))
            self.assertTrue(services.allow_request(request(nonce="other"), "issue"))

    def test_unrelated_ip_and_action_are_independent(self):
        with at(1_000_000):
            for _ in range(3):
                services.allow_request(request(), "issue")
            self.assertTrue(services.allow_request(request("other", "192.0.2.2"), "issue"))
            self.assertTrue(services.allow_request(request(), "verify"))

    @override_settings(NOVA_SLIDER_RATE_LIMITS={"issue_ip": 1, "issue_session": 3})
    def test_session_denial_does_not_refund_ip_and_retry_includes_new_ip_debt(self):
        now = 120_000_000
        session_key = scope_key(scope="session", subject="session-a")
        # Session is one microsecond short of allowing another request.
        RateLimitState.objects.create(key=session_key, tat_us=now + 40_000_001)
        with at(now):
            denied = services.allow_request(request(), "issue")
        self.assertFalse(denied)
        self.assertEqual(denied.retry_after, 60)
        self.assertEqual(RateLimitState.objects.get(pk=scope_key()).tat_us, now + 60_000_000)
        self.assertEqual(RateLimitState.objects.get(pk=session_key).tat_us, now + 40_000_001)

    def test_migrated_block_uses_exact_boundary_without_mutating_denied_state(self):
        RateLimitState.objects.create(key=scope_key(), blocked_until_us=80_000_001)
        with at(20_000_000):
            self.assertEqual(services.allow_request(request(), "issue").retry_after, 61)
        state = RateLimitState.objects.get(pk=scope_key())
        self.assertEqual((state.tat_us, state.blocked_until_us), (0, 80_000_001))
        with at(80_000_000):
            self.assertFalse(services.allow_request(request(), "issue"))
        with at(80_000_001):
            self.assertTrue(services.allow_request(request(), "issue"))

    def test_demo_and_login_purposes_share_action_quota(self):
        client = self.client_with_init()
        with at(1_000_000):
            for purpose in ("demo", "login", "demo"):
                self.assertEqual(self.post(client, "challenge", {"purpose": purpose}).status_code, 200)
            denied = self.post(client, "challenge", {"purpose": "login"})
        self.assertEqual(denied.status_code, 429)
        self.assertEqual(denied.json()["retryAfter"], 20)
        self.assertEqual(RateLimitState.objects.filter(key__startswith="issue:").count(), 2)

    def test_retry_header_and_body_are_actual_wait_seconds(self):
        client = self.client_with_init()
        with at(1_000_000):
            for _ in range(3):
                self.assertEqual(self.post(client, "challenge", {"purpose": "bad"}).status_code, 400)
        with at(1_000_001):
            response = self.post(client, "challenge", {"purpose": "demo"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "20")
        self.assertEqual(response.json(), {"ok": False, "code": "rate_limited", "attemptsRemaining": 0, "retryAfter": 20})
        self.assertIn("no-store", response["Cache-Control"])
        with at(20_999_999):
            response = self.post(client, "challenge", {"purpose": "demo"})
        self.assertEqual(response["Retry-After"], "1")
        self.assertFalse(Challenge.objects.exists())

    def test_database_failure_is_503_and_never_issues_or_verifies(self):
        client = self.client_with_init()
        for endpoint in ("challenge", "verify"):
            with patch.object(RateLimitState.objects, "get_or_create", side_effect=DatabaseError("secret database details")):
                with patch.object(services, "issue") as issue, patch.object(services, "verify") as verify:
                    response = self.post(client, endpoint, {"purpose": "demo"})
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json()["code"], "rate_limit_unavailable")
                    self.assertNotIn("secret", response.content.decode())
                    issue.assert_not_called()
                    verify.assert_not_called()

    def test_fast_update_database_failure_is_503_even_for_existing_scopes(self):
        client = self.client_with_init()
        with at(1_000_000):
            self.assertTrue(services.allow_request(self.request(client), "issue"))
            with patch("django.db.models.query.QuerySet.update", side_effect=DatabaseError("private failure")):
                with patch.object(services, "issue") as issue:
                    response = self.post(client, "challenge", {"purpose": "demo"})
                    self.assertEqual(response.status_code, 503)
                    self.assertEqual(response.json()["code"], "rate_limit_unavailable")
                    self.assertNotIn("private", response.content.decode())
                    issue.assert_not_called()

    def test_cleanup_only_removes_fully_refilled_unblocked_states(self):
        now = 120_000_000
        RateLimitState.objects.create(key="idle", tat_us=now, blocked_until_us=now)
        RateLimitState.objects.create(key="live", tat_us=now + 1)
        RateLimitState.objects.create(key="blocked", blocked_until_us=now + 1)
        with at(now):
            call_command("prune_slider_captcha", stdout=io.StringIO())
        self.assertEqual(set(RateLimitState.objects.values_list("key", flat=True)), {"live", "blocked"})

    def test_quota_cleanup_keeps_sql_predicate_even_when_delete_signals_exist(self):
        RateLimitState.objects.create(key="idle", tat_us=1_000_000)
        listener = Mock()
        post_delete.connect(listener, sender=RateLimitState, weak=False)
        try:
            with at(1_000_000), CaptureQueriesContext(connection) as captured:
                call_command("prune_slider_captcha", stdout=io.StringIO())
        finally:
            post_delete.disconnect(listener, sender=RateLimitState)
        deletes = [query["sql"] for query in captured.captured_queries
                   if "DELETE FROM" in query["sql"] and "nova_slider_captcha_ratelimitstate" in query["sql"]]
        self.assertEqual(len(deletes), 1)
        self.assertIn('"tat_us" <=', deletes[0])
        self.assertIn('"blocked_until_us" <=', deletes[0])
        listener.assert_not_called()  # Quota housekeeping is deliberately SQL-only.
        self.assertFalse(RateLimitState.objects.exists())


class RateSettingsTests(SimpleTestCase):
    def test_unsafe_or_unknown_configuration_is_rejected(self):
        for value in (None, [], "unbounded", {"issue_ip": True}, {"issue_ip": 0}, {"issue_ip": -1},
                      {"issue_ip": 1.0}, {"issue_ip": "3"}, {"issue_ip": MAX_RATE_LIMIT + 1},
                      {"issue_ip": 10**1000}, {"issu_ip": 3}):
            with self.subTest(value=value), override_settings(NOVA_SLIDER_RATE_LIMITS=value):
                with self.assertRaises(ValueError):
                    rate_limit("issue", "ip")
                self.assertIn("nova_slider_captcha.E003", [error.id for error in captcha_settings_check(None)])

    def test_supported_configuration_boundaries_and_default(self):
        with override_settings(NOVA_SLIDER_RATE_LIMITS={"issue_ip": 1, "verify_ip": MAX_RATE_LIMIT}):
            self.assertEqual(rate_limit("issue", "ip"), 1)
            self.assertEqual(rate_limit("verify", "ip"), MAX_RATE_LIMIT)
            self.assertEqual(rate_limit("issue", "session"), 20)

    def test_exact_timestamp_does_not_round_microseconds(self):
        now = datetime(2026, 10, 5, 1, 2, 3, 999999, tzinfo=datetime_timezone.utc)
        self.assertEqual(services.timestamp_us(now + timedelta(microseconds=1)) - services.timestamp_us(now), 1)

    @override_settings(USE_TZ=False, TIME_ZONE="Asia/Shanghai")
    def test_naive_timestamps_use_default_timezone(self):
        local = datetime(2026, 10, 5, 8, 0, 0, 999999)
        utc = datetime(2026, 10, 5, 0, 0, 0, 999999, tzinfo=datetime_timezone.utc)
        self.assertEqual(services.timestamp_us(local), services.timestamp_us(utc))

    def test_real_upgrade_retains_live_limits_and_refuses_unsafe_reversal(self):
        self._run_upgrade()

    def test_real_upgrade_preserves_legacy_naive_datetime_expiries(self):
        self._run_upgrade("--naive-time")

    def _run_upgrade(self, *args):
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "scripts/test_rate_upgrade.py"), *args],
                                capture_output=True, text=True, env=os.environ.copy(), timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Legacy upgrade and rollback guard passed", result.stdout)
