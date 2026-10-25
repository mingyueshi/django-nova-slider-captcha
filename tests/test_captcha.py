import base64
import io
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.db import close_old_connections
from django.test import Client, RequestFactory, TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from PIL import Image

from nova_slider_captcha import services
from nova_slider_captcha.forms import SliderAdminAuthenticationForm
from nova_slider_captcha.models import Challenge, RateBucket, RateLimitState


class CaptchaHelpers:
    def client_with_init(self, csrf=False):
        client = Client(enforce_csrf_checks=csrf)
        response = client.get("/captcha/init")
        self.assertEqual(response.status_code, 200)
        client.csrf = response.json()["csrfToken"]
        return client

    def post(self, client, endpoint, data, **extra):
        return client.post("/captcha/" + endpoint, json.dumps(data), content_type="application/json", HTTP_X_CSRFTOKEN=client.csrf, **extra)

    def challenge(self, client, purpose="demo"):
        result = self.post(client, "challenge", {"purpose": purpose})
        self.assertEqual(result.status_code, 200, result.content)
        return result.json(), Challenge.objects.get(pk=result.json()["challengeId"])

    def token(self, client, purpose="demo"):
        challenge, stored = self.challenge(client, purpose)
        response = self.post(client, "verify", {"challengeId": challenge["challengeId"], "x": stored.target_x})
        self.assertTrue(response.json()["ok"], response.content)
        return response.json()["token"], stored

    def request(self, client):
        request = RequestFactory().get("/")
        request.session = client.session
        return request


class CaptchaTests(CaptchaHelpers, TestCase):
    def setUp(self):
        self.client = self.client_with_init()

    def test_init_establishes_csrf_and_no_store(self):
        response = self.client.get("/captcha/init")
        self.assertIn("csrfToken", response.json())
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("csrftoken", response.cookies)
        binding = services.session_binding(self.request(self.client))
        self.client.get("/captcha/init")
        self.assertEqual(binding, services.session_binding(self.request(self.client)))

    def test_requires_init_before_challenge(self):
        client = Client()
        response = client.post("/captcha/challenge", '{"purpose":"demo"}', content_type="application/json")
        self.assertEqual(response.status_code, 409)
        self.assertFalse(Challenge.objects.exists())

    def test_response_contains_only_public_fields_and_pngs(self):
        data, stored = self.challenge(self.client)
        self.assertEqual(set(data), {"challengeId", "background", "piece", "width", "height", "pieceWidth", "pieceY", "expiresIn", "maxAttempts"})
        self.assertEqual((data["width"], data["height"], data["pieceWidth"]), (320, 160, 44))
        self.assertEqual((data["expiresIn"], data["maxAttempts"]), (120, 5))
        for field, size in (("background", (320, 160)), ("piece", (44, 44))):
            self.assertTrue(data[field].startswith("data:image/png;base64,"))
            image = Image.open(io.BytesIO(base64.b64decode(data[field].split(",")[1])))
            self.assertEqual(image.size, size)
            self.assertEqual(image.format, "PNG")
            self.assertFalse(image.info)
        self.assertTrue(0 <= stored.target_x <= 276)

    def test_success_one_use_and_only_hash_in_database(self):
        token, stored = self.token(self.client)
        stored.refresh_from_db()
        self.assertNotEqual(stored.token_hash, token)
        self.assertEqual(len(token), 43)
        response = self.post(self.client, "submit", {"token": token, "purpose": "demo"})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["ok"])
        self.assertEqual(self.post(self.client, "submit", {"token": token, "purpose": "demo"}).status_code, 403)

    def test_tolerance_boundaries(self):
        for delta, success in ((-4, True), (4, True), (-4.01, False), (4.01, False)):
            data, stored = self.challenge(self.client)
            result = self.post(self.client, "verify", {"challengeId": data["challengeId"], "x": stored.target_x + delta}).json()
            self.assertEqual(result["ok"], success)

    def test_attempt_limit_is_five(self):
        data, stored = self.challenge(self.client)
        for expected in (4, 3, 2, 1, 0):
            result = self.post(self.client, "verify", {"challengeId": data["challengeId"], "x": 0}).json()
            self.assertFalse(result["ok"])
            self.assertEqual(result["attemptsRemaining"], expected)
        result = self.post(self.client, "verify", {"challengeId": data["challengeId"], "x": stored.target_x}).json()
        self.assertEqual(result["code"], "attempts_exhausted")
        stored.refresh_from_db()
        self.assertEqual(stored.attempts, 5)

    def test_expired_challenge(self):
        data, stored = self.challenge(self.client)
        Challenge.objects.filter(pk=stored.pk).update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.post(self.client, "verify", {"challengeId": data["challengeId"], "x": stored.target_x}).json()["code"], "expired")

    def test_expired_token(self):
        token, stored = self.token(self.client)
        Challenge.objects.filter(pk=stored.pk).update(token_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertFalse(services.consume(token, self.request(self.client), "demo"))

    def test_cross_session_verify_does_not_use_attempts(self):
        data, stored = self.challenge(self.client)
        other = self.client_with_init()
        self.assertEqual(self.post(other, "verify", {"challengeId": data["challengeId"], "x": stored.target_x}).json()["code"], "invalid_challenge")
        stored.refresh_from_db()
        self.assertEqual(stored.attempts, 0)

    def test_cross_session_token_is_rejected_without_consuming(self):
        token, _ = self.token(self.client)
        self.assertFalse(services.consume(token, self.request(self.client_with_init()), "demo"))
        self.assertTrue(services.consume(token, self.request(self.client), "demo"))

    def test_cross_purpose_token_is_rejected_without_consuming(self):
        token, _ = self.token(self.client, "login")
        self.assertFalse(services.consume(token, self.request(self.client), "demo"))
        self.assertTrue(services.consume(token, self.request(self.client), "login"))

    def test_solved_challenge_cannot_issue_more_tokens(self):
        token, stored = self.token(self.client)
        result = self.post(self.client, "verify", {"challengeId": str(stored.pk), "x": stored.target_x}).json()
        self.assertEqual(result["code"], "already_verified")
        self.assertNotIn("token", result)

    def test_malformed_positions(self):
        data, stored = self.challenge(self.client)
        for x in (None, True, False, [], {}, "100", -1, 277, float("nan"), float("inf"), 10**1000):
            response = self.post(self.client, "verify", {"challengeId": data["challengeId"], "x": x})
            self.assertEqual(response.status_code, 400, str(x))
        stored.refresh_from_db()
        self.assertEqual(stored.attempts, 0)

    def test_malformed_json_and_purpose(self):
        for body in ("{", "[]", '"a"', "null", "[" * 1500 + "]" * 1500):
            response = self.client.post("/captcha/challenge", body, content_type="application/json")
            self.assertEqual(response.status_code, 400)
        for purpose in (None, [], {}, True, "admin", "login "):
            self.assertEqual(self.post(self.client, "challenge", {"purpose": purpose}).status_code, 400)
        self.assertEqual(self.client.post("/captcha/challenge", "x", content_type="text/plain").status_code, 415)
        self.assertEqual(self.client.post("/captcha/challenge", "x" * 4097, content_type="application/json").status_code, 413)

    def test_malformed_ids_and_tokens(self):
        for challenge_id in (None, {}, [], "a", "x" * 36):
            self.assertEqual(self.post(self.client, "verify", {"challengeId": challenge_id, "x": 100}).status_code, 400)
        for token in (None, [], {}, True, "", "x" * 43, "x" * 5000):
            self.assertFalse(services.consume(token, self.request(self.client), "demo"))

    def test_proof_generation_and_consumption_share_encoded_length(self):
        token, _ = self.token(self.client)
        self.assertEqual(services.TOKEN_BYTES, 32)
        self.assertEqual(len(token), services.TOKEN_LENGTH)
        self.assertEqual(services.TOKEN_LENGTH, (services.TOKEN_BYTES * 8 + 5) // 6)
        self.assertFalse(services.consume(token + "x", self.request(self.client), "demo"))
        self.assertFalse(services.consume(token[:-1], self.request(self.client), "demo"))
        self.assertTrue(services.consume(token, self.request(self.client), "demo"))

    def test_same_origin_enforced_even_for_csrf_trusted_origin(self):
        with override_settings(CSRF_TRUSTED_ORIGINS=["https://unrelated.example"]):
            self.assertEqual(self.post(self.client, "challenge", {"purpose": "demo"}, HTTP_ORIGIN="https://unrelated.example").status_code, 403)
            self.assertEqual(self.post(self.client, "challenge", {"purpose": "demo"}, HTTP_SEC_FETCH_SITE="cross-site").status_code, 403)
            self.assertEqual(self.post(self.client, "challenge", {"purpose": "demo"}, HTTP_SEC_FETCH_SITE="same-site").status_code, 403)
        self.assertEqual(self.post(self.client, "challenge", {"purpose": "demo"}, HTTP_ORIGIN="http://testserver").status_code, 200)

    def test_csrf_is_required_for_every_post_route(self):
        client = self.client_with_init(csrf=True)
        for endpoint in ("challenge", "verify", "submit", "demo"):
            self.assertEqual(client.post("/captcha/" + endpoint, "{}", content_type="application/json").status_code, 403)
        self.assertEqual(self.post(client, "challenge", {"purpose": "demo"}).status_code, 200)

    def test_only_post_mutates(self):
        for endpoint in ("challenge", "verify", "submit", "demo"):
            self.assertEqual(self.client.get("/captcha/" + endpoint).status_code, 405)
        self.assertFalse(Challenge.objects.exists())

    @override_settings(NOVA_SLIDER_RATE_LIMITS={"issue_session": 2})
    def test_issue_session_rate_limit(self):
        self.challenge(self.client)
        self.challenge(self.client)
        response = self.post(self.client, "challenge", {"purpose": "demo"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "30")
        self.assertEqual(response.json()["retryAfter"], 30)

    @override_settings(NOVA_SLIDER_RATE_LIMITS={"issue_ip": 2})
    def test_ip_limit_survives_session_changes_and_ignores_forwarded_header(self):
        for _ in range(2):
            self.challenge(self.client_with_init())
        self.assertEqual(self.post(self.client_with_init(), "challenge", {"purpose": "demo"}, HTTP_X_FORWARDED_FOR="8.8.8.8").status_code, 429)

    @override_settings(NOVA_SLIDER_RATE_LIMITS={"verify_session": 2})
    def test_verify_rate_limit_includes_malformed_requests(self):
        for _ in range(2):
            self.assertEqual(self.post(self.client, "verify", {"x": 0}).status_code, 400)
        self.assertEqual(self.post(self.client, "verify", {"x": 0}).status_code, 429)

    def test_prune_preserves_live_token(self):
        token, stored = self.token(self.client)
        old = Challenge.objects.create(session_hash="old", purpose="demo", target_x=70, expires_at=timezone.now() - timedelta(minutes=6))
        RateBucket.objects.create(key="old", count=1, expires_at=timezone.now() - timedelta(seconds=1))
        call_command("prune_slider_captcha", stdout=io.StringIO())
        self.assertFalse(Challenge.objects.filter(pk=old.pk).exists())
        self.assertFalse(RateBucket.objects.filter(pk="old").exists())
        self.assertTrue(services.consume(token, self.request(self.client), "demo"))

    def test_admin_get_renders_widget_and_media(self):
        response = self.client.get("/admin/login/")
        self.assertContains(response, "<nova-slider")
        self.assertContains(response, 'id="id_nova_slider_token"')
        self.assertContains(response, "nova_slider_captcha/slider.js")
        if "nova_admin" in settings.INSTALLED_APPS:
            self.assertContains(response, "nova-login-layout")
        else:
            self.assertNotContains(response, "nova-login-layout")

    def test_admin_missing_token_fails_before_authentication(self):
        with patch("django.contrib.auth.forms.authenticate") as authenticate:
            form = SliderAdminAuthenticationForm(self.request(self.client), data={"username": "admin", "password": "password"})
            self.assertFalse(form.is_valid())
            authenticate.assert_not_called()

    def test_admin_demo_token_rejected(self):
        token, _ = self.token(self.client, "demo")
        with patch("django.contrib.auth.forms.authenticate") as authenticate:
            form = SliderAdminAuthenticationForm(self.request(self.client), data={"username": "admin", "password": "password", "nova_slider_token": token})
            self.assertFalse(form.is_valid())
            authenticate.assert_not_called()

    def test_admin_login_success_and_proof_consumed(self):
        get_user_model().objects.create_superuser("admin", "admin@example.com", "password")
        token, _ = self.token(self.client, "login")
        response = self.client.post("/admin/login/?next=/admin/", {"username": "admin", "password": "password", "nova_slider_token": token, "next": "/admin/"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/admin/")
        self.assertIn("_auth_user_id", self.client.session)
        self.assertFalse(services.consume(token, self.request(self.client), "login"))

    def test_bad_password_consumes_proof(self):
        token, _ = self.token(self.client, "login")
        form = SliderAdminAuthenticationForm(self.request(self.client), data={"username": "missing", "password": "wrong", "nova_slider_token": token})
        self.assertFalse(form.is_valid())
        self.assertFalse(services.consume(token, self.request(self.client), "login"))


class AtomicityTests(CaptchaHelpers, TransactionTestCase):
    def setUp(self):
        self.client = self.client_with_init()

    def parallel(self, fn, count=8):
        barrier = Barrier(count)
        def worker(index):
            close_old_connections()
            try:
                barrier.wait(timeout=10)
                return fn(index)
            finally:
                close_old_connections()
        with ThreadPoolExecutor(max_workers=count) as executor:
            return list(executor.map(worker, range(count)))

    def test_token_race_allows_exactly_one_consumer(self):
        token, _ = self.token(self.client)
        session = dict(self.client.session)
        def consume(_):
            request = RequestFactory().get("/")
            request.session = session.copy()
            return services.consume(token, request, "demo")
        self.assertEqual(self.parallel(consume).count(True), 1)

    def test_verify_race_issues_exactly_one_token(self):
        _, stored = self.challenge(self.client)
        session = dict(self.client.session)
        def verify(_):
            request = RequestFactory().get("/")
            request.session = session.copy()
            return services.verify(request, stored.pk, stored.target_x)
        self.assertEqual(sum(result["ok"] for result in self.parallel(verify)), 1)
        stored.refresh_from_db()
        self.assertEqual(stored.attempts, 1)

    def test_wrong_answer_race_never_exceeds_max_attempts(self):
        _, stored = self.challenge(self.client)
        session = dict(self.client.session)
        def verify(_):
            request = RequestFactory().get("/")
            request.session = session.copy()
            return services.verify(request, stored.pk, 0)
        self.parallel(verify, 12)
        stored.refresh_from_db()
        self.assertEqual(stored.attempts, 5)
        self.assertFalse(stored.solved)

    @override_settings(NOVA_SLIDER_RATE_LIMITS={"issue_session": 3})
    def test_rate_limit_creation_race_is_atomic(self):
        session = dict(self.client.session)
        def allowed(_):
            request = RequestFactory().get("/")
            request.session = session.copy()
            return bool(services.allow_request(request, "issue"))
        # Fix the clock: out-of-order wall timestamps are conservatively treated
        # as a backward-clock step and may legitimately admit fewer requests.
        with patch("nova_slider_captcha.services.timezone.now", return_value=timezone.now()):
            self.assertEqual(self.parallel(allowed).count(True), 3)

    @override_settings(NOVA_SLIDER_RATE_LIMITS={"issue_ip": 3, "issue_session": 100})
    def test_ip_limit_creation_race_across_new_sessions_is_atomic(self):
        def allowed(index):
            request = RequestFactory().get("/")
            request.session = {"_nova_slider_binding": f"new-session-{index}"}
            return bool(services.allow_request(request, "issue"))
        now = timezone.now()
        with patch("nova_slider_captcha.services.timezone.now", return_value=now):
            self.assertEqual(self.parallel(allowed, 12).count(True), 3)
        self.assertEqual(RateLimitState.objects.count(), 4)

    @override_settings(NOVA_SLIDER_RATE_LIMITS={"issue_ip": 3, "issue_session": 3})
    def test_concurrent_refill_allows_one_and_denials_preserve_debt(self):
        session = dict(self.client.session)
        def allowed(_):
            request = RequestFactory().get("/")
            request.session = session.copy()
            return bool(services.allow_request(request, "issue"))
        now = timezone.now()
        with patch("nova_slider_captcha.services.timezone.now", return_value=now):
            self.assertEqual([allowed(0) for _ in range(3)], [True, True, True])
            before = list(RateLimitState.objects.order_by("key").values())
            self.assertFalse(any(self.parallel(allowed, 12)))
            self.assertEqual(before, list(RateLimitState.objects.order_by("key").values()))
        with patch("nova_slider_captcha.services.timezone.now", return_value=now + timedelta(seconds=20)):
            self.assertEqual(self.parallel(allowed, 12).count(True), 1)
