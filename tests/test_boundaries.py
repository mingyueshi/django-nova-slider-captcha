"""Session creation, Admin validation and primary/replica consistency boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch

from django import forms
from django.contrib.sessions.models import Session
from django.db import DatabaseError, connections
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from nova_slider_captcha import services
from nova_slider_captcha.checks import captcha_settings_check
from nova_slider_captcha.conf import rate_limit
from nova_slider_captcha.forms import SliderAdminAuthenticationForm, SliderCaptchaField, SliderCaptchaFormMixin
from nova_slider_captcha.models import Challenge, RateLimitState
from tests.test_captcha import CaptchaHelpers
from tests.test_rate_limit import at, request, scope_key


@override_settings(NOVA_SLIDER_RATE_LIMITS={"init_ip": 2})
class InitBoundaryTests(CaptchaHelpers, TestCase):
    def test_rejected_init_does_not_create_session_or_csrf_in_response_middleware(self):
        for csrf_sessions in (False, True):
            with self.subTest(csrf_sessions=csrf_sessions), override_settings(CSRF_USE_SESSIONS=csrf_sessions), at(1_000_000):
                RateLimitState.objects.all().delete()
                start = Session.objects.count()
                clients = [self.client_with_init(csrf=True) for _ in range(2)]
                self.assertEqual(Session.objects.count(), start + 2)
                key = scope_key("init", subject="127.0.0.1")
                debt = RateLimitState.objects.get(pk=key).tat_us
                for _ in range(3):
                    denied = Client(enforce_csrf_checks=True).get("/captcha/init", HTTP_X_FORWARDED_FOR="192.0.2.99")
                    self.assertEqual(denied.status_code, 429)
                    self.assertEqual(denied["Retry-After"], "30")
                    self.assertEqual(denied.json()["retryAfter"], 30)
                    self.assertNotIn("sessionid", denied.cookies)
                    self.assertNotIn("csrftoken", denied.cookies)
                    rejected = Client().get("/captcha/init", HTTP_ORIGIN="https://other.example")
                    self.assertEqual(rejected.status_code, 403)
                    self.assertFalse(rejected.cookies)
                self.assertEqual(Session.objects.count(), start + 2)
                self.assertEqual(RateLimitState.objects.get(pk=key).tat_us, debt)
                # A valid existing binding does not spend the creation quota.
                self.assertEqual(clients[0].get("/captcha/init").status_code, 200)
                self.assertEqual(Session.objects.count(), start + 2)
                self.assertEqual(RateLimitState.objects.get(pk=key).tat_us, debt)
                # Accepted init still yields a usable CSRF token in both modes.
                self.assertEqual(self.post(clients[0], "challenge", {"purpose": "demo"}).status_code, 200)

    def test_exact_refill_ip_isolation_and_no_binding_in_limiter(self):
        req = request()
        req.session = {}
        with at(1_000_000):
            self.assertTrue(services.allow_request(req, "init"))
            self.assertTrue(services.allow_request(req, "init"))
            self.assertFalse(services.allow_request(req, "init"))
            self.assertTrue(services.allow_request(request(ip="192.0.2.2"), "init"))
        self.assertEqual(req.session, {})
        self.assertFalse(RateLimitState.objects.filter(key__startswith="init:session:").exists())
        with at(30_999_999):
            self.assertEqual(services.allow_request(req, "init").retry_after, 1)
        with at(31_000_000):
            self.assertTrue(services.allow_request(req, "init"))

    def test_invalid_init_settings_and_database_failures_never_create_sessions(self):
        for csrf_sessions in (False, True):
            with override_settings(CSRF_USE_SESSIONS=csrf_sessions):
                for value in (True, 0, -1, 1.5, "2", 60001):
                    with self.subTest(value=value), override_settings(NOVA_SLIDER_RATE_LIMITS={"init_ip": value}):
                        self.assertIn("nova_slider_captcha.E003", [error.id for error in captcha_settings_check(None)])
                        response = Client().get("/captcha/init")
                        self.assertEqual((response.status_code, response.json()["code"]), (503, "configuration_invalid"))
                        self.assertFalse(response.cookies)
                with patch.object(RateLimitState.objects, "get_or_create", side_effect=DatabaseError("private")):
                    response = Client().get("/captcha/init")
                    self.assertEqual((response.status_code, response.json()["code"]), (503, "rate_limit_unavailable"))
                    self.assertFalse(response.cookies)
                with patch.object(services, "session_binding", side_effect=DatabaseError("private")):
                    response = Client().get("/captcha/init")
                    self.assertEqual((response.status_code, response.json()["code"]), (503, "unavailable"))
                    self.assertFalse(response.cookies)
        self.assertFalse(Session.objects.exists())

    def test_missing_session_capability_is_controlled_and_issue_has_no_side_effects(self):
        middleware = ["django.middleware.csrf.CsrfViewMiddleware"]
        with override_settings(MIDDLEWARE=middleware):
            response = Client().get("/captcha/init")
            self.assertEqual((response.status_code, response.json()["code"]), (503, "configuration_invalid"))
            self.assertFalse(response.cookies)
            response = Client().post("/captcha/challenge", '{"purpose":"demo"}', content_type="application/json")
            self.assertEqual((response.status_code, response.json()["code"]), (409, "init_required"))
        with patch.object(services, "make_puzzle") as image, self.assertNumQueries(0):
            with self.assertRaisesMessage(ValueError, "session binding"):
                services.issue(RequestFactory().get("/"), "demo")
            image.assert_not_called()
        self.assertFalse(Challenge.objects.exists())
        self.assertFalse(RateLimitState.objects.exists())

    def test_non_string_binding_cannot_report_success_or_generate_csrf(self):
        client = Client()
        session = client.session
        session["_nova_slider_binding"] = 123
        session.save()
        with patch("nova_slider_captcha.views.get_token") as csrf:
            response = client.get("/captcha/init")
            self.assertEqual((response.status_code, response.json()["code"]), (503, "configuration_invalid"))
            self.assertFalse(response.cookies)
            csrf.assert_not_called()

    def test_init_default_and_dynamic_configuration(self):
        with override_settings(NOVA_SLIDER_RATE_LIMITS={}):
            self.assertEqual(rate_limit("init", "ip"), 40)
        with override_settings(NOVA_SLIDER_RATE_LIMITS={"init_ip": 1}), at(1_000_000):
            self.client_with_init()
            self.assertEqual(Client().get("/captcha/init").status_code, 429)
        with override_settings(NOVA_SLIDER_RATE_LIMITS={"init_ip": 3}):
            with at(20_999_999):
                self.assertEqual(Client().get("/captcha/init").status_code, 429)
            with at(21_000_000):
                self.assertEqual(Client().get("/captcha/init").status_code, 200)


class AdminFieldBoundaryTests(CaptchaHelpers, TestCase):
    def test_field_errors_preserve_proof_and_skip_authentication(self):
        class ExtendedLogin(SliderAdminAuthenticationForm):
            extra = forms.CharField()

        client = self.client_with_init()
        token, row = self.token(client, "login")
        cases = [({"password": "secret"}, "username"), ({"username": " ", "password": "secret"}, "username"),
                 ({"username": "admin"}, "password"), ({"username": "admin", "password": "secret"}, "extra")]
        for data, field in cases:
            data = {**data, "nova_slider_token": token}
            form_type = ExtendedLogin if field == "extra" else SliderAdminAuthenticationForm
            with self.subTest(field=field), patch("nova_slider_captcha.forms.consume") as consume, patch("django.contrib.auth.forms.authenticate") as authenticate:
                form = form_type(self.request(client), data=data)
                self.assertFalse(form.is_valid())
                self.assertIn(field, form.errors)
                self.assertNotIn(token, form.as_p())
                consume.assert_not_called()
                authenticate.assert_not_called()
            row.refresh_from_db()
            self.assertFalse(row.token_consumed)
        response = client.post("/admin/login/", {"password": "secret", "nova_slider_token": token})
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, token)
        row.refresh_from_db()
        self.assertFalse(row.token_consumed)

    def test_complete_bad_password_consumes_before_authentication(self):
        client = self.client_with_init()
        token, row = self.token(client, "login")
        def authenticate(*args, **kwargs):
            row.refresh_from_db()
            self.assertTrue(row.token_consumed)
            return None
        with patch("django.contrib.auth.forms.authenticate", side_effect=authenticate) as auth:
            form = SliderAdminAuthenticationForm(self.request(client), data={"username": "missing", "password": "wrong", "nova_slider_token": token})
            self.assertFalse(form.is_valid())
            self.assertEqual(auth.call_count, 1)
            self.assertNotIn(token, form.as_p())


class CaptchaReplicaRouter:
    def db_for_read(self, model, **hints):
        return "replica" if model._meta.app_label == "nova_slider_captcha" else None

    def db_for_write(self, model, **hints):
        return "captcha" if model._meta.app_label == "nova_slider_captcha" else None


@override_settings(DATABASE_ROUTERS=[CaptchaReplicaRouter()])
class WriterConsistencyTests(TestCase):
    databases = {"default", "captcha", "replica"}

    def setUp(self):
        self.req = request()

    def issue(self):
        data = services.issue(self.req, "demo")
        return Challenge.objects.using("captcha").get(pk=data["challengeId"])

    def token(self):
        row = self.issue()
        return services.verify(self.req, row.pk, row.target_x)["token"], row

    def test_new_challenge_verifies_without_replication_and_token_consumes_once(self):
        row = self.issue()
        with CaptureQueriesContext(connections["replica"]) as replica:
            result = services.verify(self.req, row.pk, row.target_x)
            self.assertTrue(result["ok"])
            self.assertTrue(services.consume(result["token"], self.req, "demo"))
            self.assertFalse(services.consume(result["token"], self.req, "demo"))
        self.assertEqual(len(replica), 0)
        self.assertFalse(Challenge.objects.using("default").exists())

    def test_stale_replica_does_not_reset_attempts_and_snapshot_race_is_rejected(self):
        row = self.issue()
        # A real separate database holds the initial, now stale snapshot.
        row.save(using="replica", force_insert=True)
        for remaining in (4, 3, 2, 1, 0):
            result = services.verify(self.req, row.pk, -100)
            self.assertEqual((result["code"], result["attemptsRemaining"]), ("incorrect", remaining))
        self.assertEqual(Challenge.objects.using("replica").get(pk=row.pk).attempts, 0)
        self.assertEqual(services.verify(self.req, row.pk, row.target_x)["code"], "attempts_exhausted")
        row = self.issue()
        from django.db.models.query import QuerySet
        original = QuerySet.first
        def raced(query):
            snapshot = original(query)
            Challenge.objects.using("captcha").filter(pk=row.pk).update(tolerance=row.tolerance + 1)
            return snapshot
        with patch.object(QuerySet, "first", raced):
            self.assertEqual(services.verify(self.req, row.pk, row.target_x)["code"], "invalid_challenge")

    def test_multi_token_rollback_and_quota_share_the_writer(self):
        class Multi(SliderCaptchaFormMixin, forms.Form):
            first = SliderCaptchaField()
            second = SliderCaptchaField()
        first, row = self.token()
        form = Multi({"first": first, "second": "x" * 43}, request=self.req)
        self.assertFalse(form.is_valid())
        row.refresh_from_db(using="captcha")
        self.assertFalse(row.token_consumed)
        second, other = self.token()
        self.assertTrue(Multi({"first": first, "second": second}, request=self.req).is_valid())
        row.refresh_from_db(using="captcha")
        other.refresh_from_db(using="captcha")
        self.assertTrue(row.token_consumed and other.token_consumed)
        with override_settings(NOVA_SLIDER_RATE_LIMITS={"issue_ip": 2, "issue_session": 2}), at(1_000_000):
            self.assertEqual([bool(services.allow_request(self.req, "issue")) for _ in range(3)], [True, True, False])
        self.assertEqual(RateLimitState.objects.using("captcha").count(), 2)
        self.assertFalse(RateLimitState.objects.using("default").exists())
        self.assertFalse(RateLimitState.objects.using("replica").exists())


class FreshSessionBackendTests(SimpleTestCase):
    def test_only_builtin_database_backends_require_sessions_app(self):
        script = Path(__file__).with_name("session_backend_probe.py")
        for backend in ("db", "cached_db", "signed_cookies", "cache", "file", "custom"):
            with self.subTest(backend=backend):
                result = subprocess.run([sys.executable, str(script), backend], env=os.environ.copy(), capture_output=True, text=True, timeout=60)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                report = json.loads(result.stdout)
                needs_app = backend in ("db", "cached_db")
                self.assertEqual(report["checks"], ["nova_slider_captcha.E008"] if needs_app else [])
                self.assertEqual(report["status"], 503 if needs_app else 200)
                self.assertEqual(report["challenge_status"], 503 if needs_app else 200)
                self.assertEqual(report["issue_rejected"], needs_app)
