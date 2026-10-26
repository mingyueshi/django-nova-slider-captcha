"""Independent public-contract acceptance, with an isolated tests.settings DB."""
import os
import sys
from unittest.mock import patch

assert os.environ.get("NOVA_TEST_DB"), "Choose a private test database"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
import django
django.setup()
from django import forms
from django.conf import settings
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.test.utils import get_runner
from django.urls import NoReverseMatch
from nova_slider_captcha.checks import captcha_settings_check
from nova_slider_captcha.conf import configured_alternative_link
from nova_slider_captcha.forms import SliderCaptchaField, SliderCaptchaFormMixin, SliderCaptchaWidget
from tests.test_captcha import CaptchaHelpers

INVALID = {"NOVA_SLIDER_ALTERNATIVE_URL": "https://invalid.example/host-private-marker",
           "NOVA_SLIDER_ALTERNATIVE_LABEL": "Host-label-private-marker"}


class RenderContracts(SimpleTestCase):
    @override_settings(**INVALID)
    def test_admin_renders_without_link_but_check_still_rejects_configuration(self):
        response = Client(raise_request_exception=False).get("/admin/login/")
        self.assertEqual(response.status_code, 200)
        html = response.content.decode()
        self.assertIn("<nova-slider", html)
        self.assertIn('name="nova_slider_token"', html)
        self.assertNotIn('class="nsc-alternative"', html)
        self.assertNotIn(INVALID["NOVA_SLIDER_ALTERNATIVE_URL"], html)
        self.assertNotIn(INVALID["NOVA_SLIDER_ALTERNATIVE_LABEL"], html)
        self.assertIn("nova_slider_captcha.E007", [error.id for error in captcha_settings_check(None)])
        with self.assertRaises(ValueError):
            configured_alternative_link()

    def test_global_configuration_is_revalidated_on_same_widget(self):
        widget = SliderCaptchaWidget()
        with override_settings(NOVA_SLIDER_ALTERNATIVE_URL="/first/", NOVA_SLIDER_ALTERNATIVE_LABEL="First"):
            self.assertIn('href="/first/"', widget.render("proof", None))
        with override_settings(**INVALID):
            self.assertNotIn('class="nsc-alternative"', widget.render("proof", None))
        with override_settings(NOVA_SLIDER_ALTERNATIVE_URL="/second/", NOVA_SLIDER_ALTERNATIVE_LABEL="Second"):
            self.assertIn('href="/second/"', widget.render("proof", None))

    @override_settings(**INVALID)
    def test_explicit_link_is_independent_and_constructor_remains_strict(self):
        widget = SliderCaptchaWidget(alternative_url="/explicit/", alternative_label="Explicit")
        self.assertIn('href="/explicit/"', widget.render("proof", None))
        with self.assertRaises(ValueError):
            SliderCaptchaWidget(alternative_url="//invalid.example/", alternative_label="Invalid")

    def test_only_expected_global_configuration_errors_are_suppressed(self):
        with patch("nova_slider_captcha.forms.configured_alternative_link", side_effect=RuntimeError("programming error")):
            with self.assertRaises(RuntimeError):
                SliderCaptchaWidget().render("proof", None)
        with self.assertRaises(NoReverseMatch):
            SliderCaptchaWidget(api_root="nonexistent:api-root").render("proof", None)


@override_settings(**INVALID)
class ProtectionContracts(CaptchaHelpers, TestCase):
    def setUp(self):
        self.client = self.client_with_init()

    def test_login_without_proof_does_not_reach_authentication(self):
        self.client.get("/admin/login/")
        with patch("django.contrib.auth.forms.authenticate") as authenticate:
            response = self.client.post("/admin/login/", {
                "username": "synthetic-user", "password": "synthetic-password",
                "csrfmiddlewaretoken": self.client.cookies["csrftoken"].value,
            })
        self.assertEqual(response.status_code, 200)
        authenticate.assert_not_called()
        self.assertIn("nova_slider_token", response.context["form"].errors)

    def test_valid_proof_is_still_required_and_consumed_once(self):
        class HostForm(SliderCaptchaFormMixin, forms.Form):
            proof = SliderCaptchaField(purpose="demo")
        request = self.request(self.client)
        self.assertFalse(HostForm({}, request=request).is_valid())
        token, row = self.token(self.client, "demo")
        form = HostForm({"proof": token}, request=request)
        self.assertNotIn('class="nsc-alternative"', form.as_p())
        self.assertTrue(form.is_valid(), form.errors)
        row.refresh_from_db()
        self.assertTrue(row.token_consumed)
        self.assertFalse(HostForm({"proof": token}, request=request).is_valid())

    def test_invalid_security_policy_still_fails_closed(self):
        with override_settings(NOVA_SLIDER_TOLERANCE=True):
            response = self.post(self.client, "challenge", {"purpose": "demo"})
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["code"], "configuration_invalid")


if __name__ == "__main__":
    sys.exit(bool(get_runner(settings)(verbosity=1, interactive=False).run_tests([__name__])))
