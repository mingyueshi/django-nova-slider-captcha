import io
import os
from pathlib import Path
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Event
from unittest.mock import patch

from django import forms
from django.conf import settings
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from nova_slider_captcha import services
from nova_slider_captcha.checks import captcha_settings_check
from nova_slider_captcha import conf
from nova_slider_captcha.conf import ChallengePolicy, challenge_policy, purposes
from nova_slider_captcha.forms import SliderCaptchaField, SliderCaptchaFormMixin
from nova_slider_captcha.models import Challenge, RateLimitState
from tests import test_captcha
from tests.test_captcha import CaptchaHelpers


class PolicySettingsTests(SimpleTestCase):
    def test_small_configuration_hits_cache_without_caching_request_purposes(self):
        with self.settings(
            NOVA_SLIDER_CHALLENGE_TTL=75, NOVA_SLIDER_MAX_ATTEMPTS=3,
            NOVA_SLIDER_TOLERANCE=0, NOVA_SLIDER_PURPOSES=["demo"],
            NOVA_SLIDER_PURPOSE_POLICIES={"demo": {"ttl": 90}},
        ):
            fields = dict(reversed(tuple(conf._POLICY_FIELDS.items())))
            conf._cached_default_policy.cache_clear()
            with patch.object(conf, "_POLICY_FIELDS", fields):
                self.assertEqual(challenge_policy(), ChallengePolicy(75, 3, 0))
            self.assertEqual(purposes(), {"demo"})
            policy_info = conf._cached_default_policy.cache_info()
            purposes_info = conf._cached_purposes.cache_info()
            for index in range(5):
                untrusted = f"unknown{index}"
                self.assertFalse(conf.valid_purpose(untrusted))
                self.assertEqual(challenge_policy(untrusted), ChallengePolicy(75, 3, 0))
            for before, after, hits in (
                (policy_info, conf._cached_default_policy.cache_info(), 5),
                (purposes_info, conf._cached_purposes.cache_info(), 10),
            ):
                self.assertEqual(after.hits, before.hits + hits)
                self.assertEqual(after.misses, before.misses)
                self.assertEqual(after.currsize, before.currsize)

    def test_large_legal_purpose_collection_bypasses_small_cache(self):
        names = [f"purpose{index}" for index in range(65)]
        with self.settings(NOVA_SLIDER_PURPOSES=names):
            before = conf._cached_purposes.cache_info()
            self.assertEqual(purposes(), frozenset(names))
            self.assertTrue(conf.valid_purpose(names[-1]))
            self.assertEqual(conf._cached_purposes.cache_info(), before)

    def test_direct_assignment_nested_overrides_and_recovery(self):
        original = challenge_policy()
        with self.settings(NOVA_SLIDER_CHALLENGE_TTL=45, NOVA_SLIDER_PURPOSES=["demo"]):
            outer = challenge_policy()
            self.assertEqual(outer.ttl, 45)
            with self.settings(NOVA_SLIDER_CHALLENGE_TTL=70, NOVA_SLIDER_PURPOSES=["login"]):
                self.assertEqual(challenge_policy().ttl, 70)
                self.assertEqual(purposes(), {"login"})
                settings.NOVA_SLIDER_CHALLENGE_TTL = []
                settings.NOVA_SLIDER_PURPOSES = [False]
                with self.assertRaises(ValueError):
                    challenge_policy()
                with self.assertRaises(ValueError):
                    purposes()
                settings.NOVA_SLIDER_CHALLENGE_TTL = 80
                settings.NOVA_SLIDER_PURPOSES = {"demo", "login"}
                self.assertEqual(challenge_policy().ttl, 80)
                self.assertEqual(purposes(), {"demo", "login"})
            self.assertEqual(challenge_policy(), outer)
            self.assertEqual(purposes(), {"demo"})
        self.assertEqual(challenge_policy(), original)
        self.assertEqual(purposes(), {"demo", "login"})

    def test_delayed_validation_cannot_replace_new_configuration(self):
        started, release = Event(), Event()
        validate = conf._policy_integer

        def delayed(value, name, minimum, maximum):
            if name == "NOVA_SLIDER_CHALLENGE_TTL" and value == 571:
                started.set()
                if not release.wait(5):
                    raise TimeoutError("old validation did not resume")
            return validate(value, name, minimum, maximum)

        conf._cached_default_policy.cache_clear()
        with (
            self.settings(NOVA_SLIDER_CHALLENGE_TTL=571),
            patch.object(conf, "_policy_integer", side_effect=delayed),
            ThreadPoolExecutor(max_workers=1) as worker,
        ):
            pending = worker.submit(challenge_policy)
            try:
                self.assertTrue(started.wait(5))
                settings.NOVA_SLIDER_CHALLENGE_TTL = 572
                self.assertEqual(challenge_policy().ttl, 572)
            finally:
                release.set()
            self.assertEqual(pending.result(timeout=5).ttl, 571)
            self.assertEqual(challenge_policy().ttl, 572)

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

    def test_dynamic_partial_overrides_inherit_globals(self):
        with override_settings(
            NOVA_SLIDER_CHALLENGE_TTL=60, NOVA_SLIDER_MAX_ATTEMPTS=7, NOVA_SLIDER_TOLERANCE=1,
            NOVA_SLIDER_PURPOSE_POLICIES={"demo": {"ttl": 30, "tolerance": 0}, "login": {}},
        ):
            self.assertEqual(challenge_policy("demo"), ChallengePolicy(30, 7, 0))
            self.assertEqual(challenge_policy("login"), challenge_policy())
            with override_settings(NOVA_SLIDER_MAX_ATTEMPTS=9):
                self.assertEqual(challenge_policy("demo").max_attempts, 9)

    def test_invalid_override_shapes_names_types_and_ranges(self):
        for table in (None, False, [], {"unknown": {}}, {1: {}}, {"login": None}, {"login": {"token_ttl": 60}}):
            with self.subTest(table=table), override_settings(NOVA_SLIDER_PURPOSE_POLICIES=table):
                with self.assertRaises(ValueError):
                    challenge_policy("demo")
                self.assertIn("nova_slider_captcha.E006", [error.id for error in captcha_settings_check(None)])
        for field, minimum, maximum in (("ttl", 30, 600), ("max_attempts", 1, 20), ("tolerance", 0, 10)):
            for value in (True, False, None, "5", 5.0, minimum - 1, maximum + 1):
                with self.subTest(field=field, value=value), override_settings(NOVA_SLIDER_PURPOSE_POLICIES={"login": {field: value}}):
                    with self.assertRaises(ValueError):
                        challenge_policy("demo")

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

    def test_in_place_mutation_preserves_snapshots_and_revokes_purpose(self):
        class ProofForm(SliderCaptchaFormMixin, forms.Form):
            proof = SliderCaptchaField(purpose="login")

        names = ["demo", "login"]
        login_policy = {"max_attempts": 2, "tolerance": 0}
        table = {"login": login_policy}
        with self.settings(NOVA_SLIDER_PURPOSES=names, NOVA_SLIDER_PURPOSE_POLICIES=table):
            token, _ = self.token(self.client, "login")
            _, pending = self.challenge(self.client, "login")
            _, disabled = self.challenge(self.client, "login")
            login_policy["tolerance"] = True
            self.assertEqual(self.post(self.client, "challenge", {"purpose": "demo"}).status_code, 503)
            login_policy["tolerance"] = 8
            _, fresh = self.challenge(self.client, "login")
            self.assertEqual(fresh.tolerance, 8)
            self.assertEqual(services.verify(self.request_obj, pending.pk, pending.target_x + 1)["code"], "incorrect")
            names.remove("login")
            self.assertEqual(self.post(self.client, "challenge", {"purpose": "demo"}).status_code, 503)
            table.clear()
            self.assertEqual(services.verify(self.request_obj, disabled.pk, disabled.target_x)["code"], "invalid_challenge")
            self.assertFalse(services.consume(token, self.request_obj, "login"))
            self.assertFalse(ProofForm({"proof": token}, request=self.request_obj).is_valid())
            names.append("login")
            self.assertTrue(ProofForm({"proof": token}, request=self.request_obj).is_valid())

    def test_purpose_snapshots_for_old_and_new_challenges(self):
        _, old = self.challenge(self.client)
        now = timezone.now()
        with override_settings(NOVA_SLIDER_PURPOSE_POLICIES={"demo": {"ttl": 30, "max_attempts": 1, "tolerance": 0}}):
            with patch("nova_slider_captcha.services.timezone.now", return_value=now):
                data, strict = self.challenge(self.client)
                inherited, login = self.challenge(self.client, "login")
            self.assertEqual((data["expiresIn"], data["maxAttempts"]), (30, 1))
            self.assertEqual((strict.expires_at, strict.max_attempts, strict.tolerance), (now + timedelta(seconds=30), 1, 0))
            self.assertEqual((inherited["expiresIn"], login.max_attempts, login.tolerance), (120, 5, 4))
            result = services.verify(self.request_obj, old.pk, old.target_x + 4)
            self.assertTrue(result["ok"])
            self.assertTrue(services.consume(result["token"], self.request_obj, "demo"))
        wrong = services.verify(self.request_obj, strict.pk, strict.target_x + 1)
        self.assertEqual((wrong["code"], wrong["attemptsRemaining"]), ("incorrect", 0))

    @override_settings(NOVA_SLIDER_PURPOSES=["demo", "login"], NOVA_SLIDER_PURPOSE_POLICIES={"login": {"ttl": 600}})
    def test_removed_purpose_and_dangling_override_fail_closed(self):
        token, _ = self.token(self.client, "login")
        _, unverified = self.challenge(self.client, "login")
        with override_settings(NOVA_SLIDER_PURPOSES=["demo"]):
            self.assertFalse(services.consume(token, self.request_obj, "login"))
            self.assertEqual(self.post(self.client, "challenge", {"purpose": "demo"}).json()["code"], "configuration_invalid")
            with override_settings(NOVA_SLIDER_PURPOSE_POLICIES={}):
                self.assertEqual(services.verify(self.request_obj, unverified.pk, unverified.target_x)["code"], "invalid_challenge")
                self.assertFalse(services.consume(token, self.request_obj, "login"))
                self.assertEqual(self.post(self.client, "challenge", {"purpose": "demo"}).status_code, 200)

    def test_invalid_unrelated_override_blocks_writes_and_invalidates_cached_form(self):
        class ProofForm(SliderCaptchaFormMixin, forms.Form):
            proof = SliderCaptchaField(purpose="demo")

        token, _ = self.token(self.client)
        form = ProofForm({"proof": token}, request=self.request_obj)
        self.assertTrue(form.is_valid())
        unused, _ = self.token(self.client)
        _, pending = self.challenge(self.client)
        before = list(RateLimitState.objects.order_by("key").values())
        with override_settings(NOVA_SLIDER_PURPOSE_POLICIES={"login": {"ttl": False}}):
            self.assertFalse(form.is_valid())
            self.assertFalse(ProofForm({"proof": unused}, request=self.request_obj).is_valid())
            with self.assertRaises(ValueError):
                services.issue(self.request_obj, "demo")
            response = self.post(self.client, "verify", {"challengeId": str(pending.pk), "x": pending.target_x})
            self.assertEqual((response.status_code, response.json()["code"]), (503, "configuration_invalid"))
            self.assertFalse(services.consume(unused, self.request_obj, "demo"))
        self.assertEqual(list(RateLimitState.objects.order_by("key").values()), before)
        self.assertFalse(form.is_valid())
        self.assertTrue(services.consume(unused, self.request_obj, "demo"))

    @override_settings(
        NOVA_SLIDER_RATE_LIMITS={"issue_session": 1, "verify_session": 1},
        NOVA_SLIDER_PURPOSE_POLICIES={"demo": {"ttl": 600}, "login": {"tolerance": 0}},
    )
    def test_configured_purposes_share_issue_and_verify_quota(self):
        _, demo = self.challenge(self.client)
        self.assertEqual(self.post(self.client, "challenge", {"purpose": "login"}).status_code, 429)
        login = services.issue(self.request_obj, "login")
        self.assertTrue(self.post(self.client, "verify", {"challengeId": str(demo.pk), "x": demo.target_x}).json()["ok"])
        self.assertEqual(self.post(self.client, "verify", {"challengeId": login["challengeId"], "x": 0}).status_code, 429)

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
