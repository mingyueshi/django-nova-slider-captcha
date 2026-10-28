"""Invalid backend configuration must remain a controlled CAPTCHA failure."""
import io
import json
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import SystemCheckError
from django.test import RequestFactory, SimpleTestCase, override_settings

from nova_slider_captcha import services, views

# An importable backend fixture with a SessionStore that is not a class.
SessionStore = None


@override_settings(INSTALLED_APPS=[app for app in settings.INSTALLED_APPS if app != "django.contrib.sessions"])
class InvalidSessionEngineTests(SimpleTestCase):
    def test_invalid_engine_reports_e008_and_fails_closed_before_side_effects(self):
        for engine in ("tests.not_a_session_engine", "types", "tests.test_session_backend", "", None):
            with self.subTest(engine=engine), override_settings(SESSION_ENGINE=engine):
                with self.assertRaises(SystemCheckError) as error:
                    call_command("check", stdout=io.StringIO(), stderr=io.StringIO())
                self.assertIn("nova_slider_captcha.E008", str(error.exception))
                self.assertNotIn("Traceback", str(error.exception))
                request = RequestFactory().get("/captcha/init")
                request.session = {}
                post = RequestFactory().post("/captcha/challenge", {"purpose": "demo"}, content_type="application/json")
                post.session = {}
                post._dont_enforce_csrf_checks = True
                # Direct view calls isolate CAPTCHA handling from a broken host
                # SessionMiddleware, which can fail before reaching any view.
                with patch("nova_slider_captcha.views.get_token") as csrf, patch("nova_slider_captcha.services.allow_request") as quota, patch("nova_slider_captcha.services.make_puzzle") as image:
                    with self.assertLogs("nova_slider_captcha", level="ERROR"):
                        for response in (views.init(request), views.challenge(post)):
                            self.assertEqual(response.status_code, 503)
                            self.assertEqual(json.loads(response.content)["code"], "configuration_invalid")
                            self.assertFalse(response.cookies)
                    with self.assertRaises(ValueError):
                        services.issue(request, "demo")
                    csrf.assert_not_called()
                    quota.assert_not_called()
                    image.assert_not_called()
                self.assertEqual(request.session, {})
                self.assertEqual(post.session, {})
