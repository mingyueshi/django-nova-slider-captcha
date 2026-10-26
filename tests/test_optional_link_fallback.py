from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from django import forms
from django.db import DatabaseError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import NoReverseMatch

from nova_slider_captcha import events, services
from nova_slider_captcha.checks import captcha_settings_check
from nova_slider_captcha.conf import configured_alternative_link
from nova_slider_captcha.forms import SliderCaptchaField, SliderCaptchaFormMixin, SliderCaptchaWidget
from tests.test_captcha import CaptchaHelpers


@override_settings(NOVA_SLIDER_ALTERNATIVE_URL="javascript:private-url", NOVA_SLIDER_ALTERNATIVE_LABEL="private-label")
class OptionalLinkRenderTests(SimpleTestCase):
    def test_global_validator_and_checks_stay_strict_but_widget_and_form_render(self):
        with self.assertRaises(ValueError):
            configured_alternative_link()
        self.assertIn("nova_slider_captcha.E007", [error.id for error in captcha_settings_check(None)])
        class ProtectedForm(SliderCaptchaFormMixin, forms.Form):
            proof = SliderCaptchaField()
        for html in (SliderCaptchaWidget().render("proof", ""), ProtectedForm().as_p()):
            self.assertIn("<nova-slider", html)
            self.assertNotIn('class="nsc-alternative"', html)
            self.assertNotIn("private-url", html)
            self.assertNotIn("private-label", html)

    def test_dynamic_recovery_and_explicit_widget_override_do_not_cache_global_validation(self):
        widget = SliderCaptchaWidget()
        self.assertNotIn('class="nsc-alternative"', widget.render("proof", ""))
        with override_settings(NOVA_SLIDER_ALTERNATIVE_URL="/secure/", NOVA_SLIDER_ALTERNATIVE_LABEL="Other"):
            self.assertIn('href="/secure/"', widget.render("proof", ""))
        self.assertNotIn('class="nsc-alternative"', widget.render("proof", ""))
        explicit = SliderCaptchaWidget(alternative_url="/specific/", alternative_label="Specific")
        with patch("nova_slider_captcha.forms.configured_alternative_link", side_effect=AssertionError("must not read global")):
            self.assertIn('href="/specific/"', explicit.render("proof", ""))
        with self.assertRaises(ValueError):
            SliderCaptchaWidget(alternative_url="javascript:explicit", alternative_label="Explicit")

    def test_other_programming_and_route_errors_propagate(self):
        with patch("nova_slider_captcha.forms.configured_alternative_link", side_effect=RuntimeError("programming error")):
            with self.assertRaises(RuntimeError):
                SliderCaptchaWidget().render("proof", "")
        with self.assertRaises(NoReverseMatch):
            SliderCaptchaWidget(api_root="missing:api-root").render("proof", "")

    def test_warning_is_fixed_low_sensitive_and_throttled_across_widgets_and_threads(self):
        with patch.object(events, "_optional_link_next_warning", 0), patch.object(events, "monotonic", return_value=100):
            with self.assertLogs("nova_slider_captcha", level="WARNING") as logs:
                def render(index):
                    return SliderCaptchaWidget().get_context(f"proof-{index}", "", {})
                with ThreadPoolExecutor(max_workers=8) as executor:
                    list(executor.map(render, range(32)))
                with patch.object(events, "monotonic", return_value=399.999):
                    render(99)
                with patch.object(events, "monotonic", return_value=400):
                    render(100)
        self.assertEqual(len(logs.records), 2)
        for record in logs.records:
            self.assertEqual(record.captcha_event, "optional_link")
            self.assertEqual(record.captcha_reason, "configuration_invalid")
            self.assertEqual(record.captcha_status, 200)
            self.assertEqual(record.captcha_action, "render")
            self.assertIsNone(record.exc_info)
            self.assertNotIn("private-url", str(record.__dict__))
            self.assertNotIn("private-label", str(record.__dict__))

    def test_broken_logging_handler_does_not_break_render_or_retry_every_time(self):
        with patch.object(events, "_optional_link_next_warning", 0), patch.object(events, "monotonic", return_value=100):
            with patch.object(events.logger, "log", side_effect=RuntimeError("handler failure")) as log:
                for _ in range(3):
                    html = SliderCaptchaWidget().render("proof", "")
                    self.assertNotIn('class="nsc-alternative"', html)
                self.assertEqual(log.call_count, 1)


@override_settings(NOVA_SLIDER_ALTERNATIVE_URL="//private.example/", NOVA_SLIDER_ALTERNATIVE_LABEL="Private")
class AdminOptionalLinkTests(CaptchaHelpers, TestCase):
    def test_admin_get_and_post_stay_available_but_missing_proof_never_authenticates(self):
        response = self.client.get("/admin/login/")
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'class="nsc-alternative"')
        self.assertNotContains(response, "private.example")
        with patch("django.contrib.auth.forms.authenticate") as authenticate:
            response = self.client.post("/admin/login/", {"username": "admin", "password": "private-password"})
            self.assertEqual(response.status_code, 200)
            self.assertNotContains(response, 'class="nsc-alternative"')
            authenticate.assert_not_called()

    def test_logger_failure_does_not_make_admin_page_500(self):
        with patch.object(events, "_optional_link_next_warning", 0), patch.object(events, "monotonic", return_value=100), patch.object(events.logger, "log", side_effect=RuntimeError("handler failure")):
            self.assertEqual(self.client.get("/admin/login/").status_code, 200)


@override_settings(NOVA_SLIDER_PURPOSES=["demo", "contact", "other"])
class FormBoundaryTests(CaptchaHelpers, TestCase):
    def setUp(self):
        self.client = self.client_with_init()
        self.request_obj = self.request(self.client)
        self.proof, self.row = self.token(self.client, "contact")

    def form_class(self):
        class ProtectedForm(SliderCaptchaFormMixin, forms.Form):
            proof = SliderCaptchaField(purpose="contact")
        return ProtectedForm

    def test_unbound_form_never_consumes(self):
        form = self.form_class()(request=self.request_obj)
        with patch("nova_slider_captcha.forms.consume") as consume:
            form.full_clean()
            self.assertFalse(form.is_valid())
            self.assertEqual(form.errors, {})
            consume.assert_not_called()

    def test_nonstring_custom_cleaner_cannot_consume_proof(self):
        form = self.form_class()({"proof": self.proof}, request=self.request_obj)
        form.clean_proof = lambda: None
        with patch("nova_slider_captcha.forms.consume") as consume:
            self.assertFalse(form.is_valid())
            consume.assert_not_called()
        self.row.refresh_from_db()
        self.assertFalse(self.row.token_consumed)

    def test_invalid_purpose_configuration_is_a_form_failure_without_consumption(self):
        with override_settings(NOVA_SLIDER_PURPOSES="contact"), patch("nova_slider_captcha.forms.consume") as consume:
            form = self.form_class()({"proof": self.proof}, request=self.request_obj)
            self.assertFalse(form.is_valid())
            consume.assert_not_called()
        self.row.refresh_from_db()
        self.assertFalse(self.row.token_consumed)

    def test_second_database_failure_rolls_back_first_real_consumption(self):
        class Multi(SliderCaptchaFormMixin, forms.Form):
            first = SliderCaptchaField(purpose="contact")
            second = SliderCaptchaField(purpose="other")
        second, row = self.token(self.client, "other")
        form = Multi({"first": self.proof, "second": second}, request=self.request_obj)
        def consume(token, request, purpose):
            if purpose == "other":
                raise DatabaseError("private database error")
            return services.consume(token, request, purpose)
        with patch("nova_slider_captcha.forms.consume", side_effect=consume):
            self.assertFalse(form.is_valid())
        self.row.refresh_from_db()
        row.refresh_from_db()
        self.assertFalse(self.row.token_consumed)
        self.assertFalse(row.token_consumed)
        self.assertIsNone(form._captcha_success)
        self.assertFalse(form._captcha_cleaning)
