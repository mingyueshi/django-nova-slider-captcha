import logging
from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase, override_settings

from nova_slider_captcha import services
from nova_slider_captcha.checks import captcha_settings_check
from nova_slider_captcha.events import logger
from tests.test_captcha import CaptchaHelpers


class BusinessLoggingTests(CaptchaHelpers, TestCase):
    def setUp(self):
        self.client = self.client_with_init()

    def test_rate_database_failure_is_structured_error_and_does_not_leak_exception(self):
        with self.assertLogs("nova_slider_captcha", level="ERROR") as logs:
            with patch("nova_slider_captcha.services.allow_request", side_effect=DatabaseError("private exception")):
                response = self.post(self.client, "challenge", {"purpose": "secret attacker input"})
        self.assertEqual(response.status_code, 503)
        record = logs.records[0]
        self.assertEqual((record.captcha_event, record.captcha_reason, record.captcha_action, record.captcha_status), ("rate_limit", "database_unavailable", "issue", 503))
        self.assertEqual(record.levelno, logging.ERROR)
        self.assertEqual(record.captcha_purpose, "unknown")
        self.assertIsNone(record.exc_info)
        self.assertNotIn("private exception", str(record.__dict__))
        self.assertNotIn("secret attacker input", str(record.__dict__))

    def test_issuance_and_consumption_database_failures_return_503_and_log(self):
        with patch("nova_slider_captcha.services.make_puzzle", side_effect=DatabaseError("private")):
            with self.assertLogs("nova_slider_captcha", level="ERROR") as logs:
                self.assertEqual(self.post(self.client, "challenge", {"purpose": "demo"}).status_code, 503)
        self.assertEqual(logs.records[0].captcha_reason, "database_unavailable")
        token, _ = self.token(self.client)
        with patch("django.db.models.query.QuerySet.update", side_effect=DatabaseError("private")):
            with self.assertLogs("nova_slider_captcha", level="ERROR") as logs:
                response = self.post(self.client, "submit", {"purpose": "demo", "token": token})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(logs.records[0].captcha_event, "consume")
        self.assertTrue(services.consume(token, self.request(self.client), "demo"))

    def test_consume_reasons_use_allowlisted_purpose_without_sensitive_values(self):
        token, row = self.token(self.client)
        request = self.request(self.client)
        secret = request.session["_nova_slider_binding"]
        with self.assertLogs("nova_slider_captcha", level="WARNING") as logs:
            self.assertFalse(services.consume(token, request, "login"))
            self.assertFalse(services.consume("raw injected\nbody", request, "untrusted\npurpose"))
            self.assertFalse(services.consume(token, None, "demo"))
        self.assertEqual([r.captcha_reason for r in logs.records], ["proof_rejected", "invalid_proof", "binding_missing"])
        self.assertEqual([r.captcha_purpose for r in logs.records], ["login", "unknown", "demo"])
        for record in logs.records:
            encoded = str(record.__dict__)
            for sensitive in (token, secret, "raw injected", "untrusted", "target_x", "session_hash", "token_hash"):
                self.assertNotIn(sensitive, encoded)
            self.assertIsNone(record.exc_info)
        self.assertTrue(services.consume(token, request, "demo"))

    def test_success_is_quiet_and_broken_handler_does_not_change_consumption(self):
        with self.assertNoLogs("nova_slider_captcha", level="DEBUG"):
            token, _ = self.token(self.client)
            self.assertTrue(services.consume(token, self.request(self.client), "demo"))
        with patch.object(logger, "log", side_effect=RuntimeError("broken handler")):
            self.assertFalse(services.consume(token, self.request(self.client), "demo"))
            self.assertFalse(services.consume("bad", None, "demo"))

    @override_settings(NOVA_SLIDER_RATE_LIMITS={"issue_session": 1})
    def test_429_default_debug_configured_warning_and_off(self):
        self.challenge(self.client)
        with self.assertNoLogs("nova_slider_captcha", level="INFO"):
            self.assertEqual(self.post(self.client, "challenge", {"purpose": "demo"}).status_code, 429)
        with override_settings(NOVA_SLIDER_RATE_LOG_LEVEL="WARNING"):
            with self.assertLogs("nova_slider_captcha", level="WARNING") as logs:
                self.assertEqual(self.post(self.client, "challenge", {"purpose": "demo"}).status_code, 429)
            self.assertEqual(logs.records[0].captcha_reason, "rate_limited")
            self.assertEqual(logs.records[0].captcha_status, 429)
            self.assertEqual(logs.records[0].levelno, logging.WARNING)
        with override_settings(NOVA_SLIDER_RATE_LOG_LEVEL="OFF"):
            with self.assertNoLogs("nova_slider_captcha", level="DEBUG"):
                self.assertEqual(self.post(self.client, "challenge", {"purpose": "demo"}).status_code, 429)
        with patch.object(logger, "log", side_effect=RuntimeError("broken handler")):
            self.assertEqual(self.post(self.client, "challenge", {"purpose": "demo"}).status_code, 429)

    def test_invalid_log_level_system_check(self):
        for value in ("VERBOSE", 20, None, []):
            with override_settings(NOVA_SLIDER_RATE_LOG_LEVEL=value):
                self.assertIn("nova_slider_captcha.E005", [e.id for e in captcha_settings_check(None)])

    def test_configuration_fault_logs_machine_code_at_error_level(self):
        with override_settings(NOVA_SLIDER_PURPOSES="demo"):
            with self.assertLogs("nova_slider_captcha", level="ERROR") as logs:
                self.assertEqual(self.post(self.client, "challenge", {"purpose": "demo"}).status_code, 503)
        self.assertEqual(logs.records[0].captcha_reason, "configuration_invalid")
