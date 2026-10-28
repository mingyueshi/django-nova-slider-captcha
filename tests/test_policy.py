import io
import os
from pathlib import Path
import subprocess
import sys
from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from nova_slider_captcha import services
from nova_slider_captcha.checks import captcha_settings_check
from nova_slider_captcha.conf import challenge_policy
from nova_slider_captcha.models import Challenge
from tests import test_captcha
from tests.test_captcha import CaptchaHelpers


class PolicySettingsTests(SimpleTestCase):
    def test_defaults_and_dynamic_boundaries(self):
        self.assertEqual((challenge_policy().ttl, challenge_policy().max_attempts, challenge_policy().tolerance), (120, 5, 4))
        for ttl, attempts, tolerance in ((30, 1, 0), (600, 20, 10)):
            with override_settings(NOVA_SLIDER_CHALLENGE_TTL=ttl, NOVA_SLIDER_MAX_ATTEMPTS=attempts, NOVA_SLIDER_TOLERANCE=tolerance):
                self.assertEqual((challenge_policy().ttl, challenge_policy().max_attempts, challenge_policy().tolerance), (ttl, attempts, tolerance))
        self.assertEqual(challenge_policy().ttl, 120)

    def test_invalid_types_and_ranges_report_check(self):
        for name, minimum, maximum in (("NOVA_SLIDER_CHALLENGE_TTL", 30, 600), ("NOVA_SLIDER_MAX_ATTEMPTS", 1, 20), ("NOVA_SLIDER_TOLERANCE", 0, 10)):
            for value in (True, False, None, "5", 5.0, [], {}, -1, minimum - 1, maximum + 1, 10**1000):
                with self.subTest(setting=name, value=value), override_settings(**{name: value}):
                    with self.assertRaises(ValueError):
                        challenge_policy()
                    self.assertIn("nova_slider_captcha.E006", [error.id for error in captcha_settings_check(None)])

    def test_existing_rows_upgrade_under_changed_settings(self):
        env = os.environ.copy()
        env.pop("PYTHONPATH", None)
        result = subprocess.run([sys.executable, str(Path(__file__).resolve().parents[1] / "scripts/test_policy_upgrade.py")], capture_output=True, text=True, env=env, timeout=60)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("preserves legacy 5/4", result.stdout)


class PolicyTests(CaptchaHelpers, TestCase):
    def setUp(self):
        self.client = self.client_with_init()
        self.request_obj = self.request(self.client)

    @override_settings(NOVA_SLIDER_CHALLENGE_TTL=600, NOVA_SLIDER_MAX_ATTEMPTS=20, NOVA_SLIDER_TOLERANCE=10)
    def test_issuance_response_and_database_snapshot(self):
        now = timezone.now()
        with patch("nova_slider_captcha.services.timezone.now", return_value=now):
            data, row = self.challenge(self.client)
        self.assertEqual((data["expiresIn"], data["maxAttempts"]), (600, 20))
        self.assertEqual((row.max_attempts, row.tolerance), (20, 10))
        self.assertEqual(row.expires_at, now + timedelta(seconds=600))
        self.assertNotIn("tolerance", data)

    def test_changing_settings_neither_enlarges_nor_shrinks_inflight_policy(self):
        with override_settings(NOVA_SLIDER_MAX_ATTEMPTS=2, NOVA_SLIDER_TOLERANCE=0):
            _, strict = self.challenge(self.client)
        with override_settings(NOVA_SLIDER_MAX_ATTEMPTS=20, NOVA_SLIDER_TOLERANCE=10):
            self.assertEqual(services.verify(self.request_obj, strict.pk, strict.target_x + 1)["attemptsRemaining"], 1)
            self.assertEqual(services.verify(self.request_obj, strict.pk, strict.target_x + 1)["attemptsRemaining"], 0)
            self.assertEqual(services.verify(self.request_obj, strict.pk, strict.target_x)["code"], "attempts_exhausted")
            _, generous = self.challenge(self.client)
        with override_settings(NOVA_SLIDER_MAX_ATTEMPTS=1, NOVA_SLIDER_TOLERANCE=0):
            self.assertEqual(services.verify(self.request_obj, generous.pk, 0)["attemptsRemaining"], 19)
            self.assertTrue(services.verify(self.request_obj, generous.pk, generous.target_x + 10)["ok"])

    def test_ttl_snapshot_boundaries_and_fixed_token_lifetime(self):
        now = timezone.now()
        with override_settings(NOVA_SLIDER_CHALLENGE_TTL=30), patch("nova_slider_captcha.services.timezone.now", return_value=now):
            _, row = self.challenge(self.client)
        with override_settings(NOVA_SLIDER_CHALLENGE_TTL=600), patch("nova_slider_captcha.services.timezone.now", return_value=now + timedelta(seconds=30)):
            self.assertEqual(services.verify(self.request_obj, row.pk, row.target_x)["code"], "expired")
        with override_settings(NOVA_SLIDER_CHALLENGE_TTL=600), patch("nova_slider_captcha.services.timezone.now", return_value=now):
            _, long = self.challenge(self.client)
        with override_settings(NOVA_SLIDER_CHALLENGE_TTL=30), patch("nova_slider_captcha.services.timezone.now", return_value=now + timedelta(seconds=599)):
            result = services.verify(self.request_obj, long.pk, long.target_x)
        self.assertTrue(result["ok"])
        self.assertEqual(result["expiresIn"], 60)
        long.refresh_from_db()
        self.assertEqual(long.token_expires_at, now + timedelta(seconds=659))

    def test_invalid_policy_fails_http_and_services_closed_without_mutation(self):
        token, solved = self.token(self.client)
        _, unsolved = self.challenge(self.client)
        before = list(Challenge.objects.order_by("id").values())
        for name, value in (("NOVA_SLIDER_CHALLENGE_TTL", 0), ("NOVA_SLIDER_MAX_ATTEMPTS", True), ("NOVA_SLIDER_TOLERANCE", 11)):
            with override_settings(**{name: value}):
                with self.assertRaises(ValueError):
                    services.issue(self.request_obj, "demo")
                with self.assertRaises(ValueError):
                    services.verify(self.request_obj, unsolved.pk, unsolved.target_x)
                self.assertFalse(services.consume(token, self.request_obj, "demo"))
                for endpoint, data in (("challenge", {"purpose": "demo"}), ("verify", {"challengeId": str(unsolved.pk), "x": unsolved.target_x}), ("submit", {"purpose": "demo", "token": token})):
                    response = self.post(self.client, endpoint, data)
                    self.assertEqual((response.status_code, response.json()["code"]), (503, "configuration_invalid"))
        self.assertEqual(list(Challenge.objects.order_by("id").values()), before)
        self.assertTrue(services.consume(token, self.request_obj, "demo"))

    @override_settings(NOVA_SLIDER_CHALLENGE_TTL=30, NOVA_SLIDER_MAX_ATTEMPTS=1, NOVA_SLIDER_TOLERANCE=0)
    def test_minimum_attempts_and_exact_tolerance(self):
        _, row = self.challenge(self.client)
        result = services.verify(self.request_obj, row.pk, row.target_x + 0.5)
        self.assertEqual((result["ok"], result["attemptsRemaining"]), (False, 0))
        self.assertEqual(services.verify(self.request_obj, row.pk, row.target_x)["code"], "attempts_exhausted")
        _, exact = self.challenge(self.client)
        self.assertTrue(services.verify(self.request_obj, exact.pk, exact.target_x)["ok"])

    @override_settings(NOVA_SLIDER_CHALLENGE_TTL=600)
    def test_prune_preserves_long_challenge_and_late_fixed_lifetime_token(self):
        now = timezone.now()
        with patch("nova_slider_captcha.services.timezone.now", return_value=now):
            _, row = self.challenge(self.client)
        with patch("nova_slider_captcha.services.timezone.now", return_value=now + timedelta(seconds=599)):
            token = services.verify(self.request_obj, row.pk, row.target_x)["token"]
        with patch("nova_slider_captcha.services.timezone.now", return_value=now + timedelta(seconds=658)):
            call_command("prune_slider_captcha", stdout=io.StringIO())
            self.assertTrue(services.consume(token, self.request_obj, "demo"))


class SnapshotAtomicityTests(CaptchaHelpers, TransactionTestCase):
    parallel = test_captcha.AtomicityTests.parallel

    def setUp(self):
        self.client = self.client_with_init()

    def test_wrong_answer_race_uses_snapshot_after_configuration_change(self):
        with override_settings(NOVA_SLIDER_MAX_ATTEMPTS=7, NOVA_SLIDER_TOLERANCE=0):
            _, row = self.challenge(self.client)
        session = dict(self.client.session)
        def verify(_):
            from types import SimpleNamespace
            return services.verify(SimpleNamespace(session=session.copy()), row.pk, 0)
        with override_settings(NOVA_SLIDER_MAX_ATTEMPTS=20, NOVA_SLIDER_TOLERANCE=10):
            results = self.parallel(verify, 12)
        row.refresh_from_db()
        self.assertEqual(row.attempts, 7)
        self.assertEqual(sum(result.get("code") == "incorrect" for result in results), 7)
        self.assertFalse(row.solved)

    def test_correct_answer_race_uses_old_tolerance_and_issues_once(self):
        with override_settings(NOVA_SLIDER_MAX_ATTEMPTS=7, NOVA_SLIDER_TOLERANCE=10):
            _, row = self.challenge(self.client)
        session = dict(self.client.session)
        def verify(_):
            from types import SimpleNamespace
            return services.verify(SimpleNamespace(session=session.copy()), row.pk, row.target_x + 10)
        with override_settings(NOVA_SLIDER_MAX_ATTEMPTS=1, NOVA_SLIDER_TOLERANCE=0):
            results = self.parallel(verify, 12)
        self.assertEqual(sum(result["ok"] for result in results), 1)
        row.refresh_from_db()
        self.assertEqual(row.attempts, 1)
