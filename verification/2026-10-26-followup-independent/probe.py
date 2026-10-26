"""Independent local acceptance; use tests.settings and a private NOVA_TEST_DB."""
import base64
import io
import json
import os
import sys
from types import ModuleType

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
assert os.environ.get("NOVA_TEST_DB"), "Choose a private test database"
import django
django.setup()

from django import forms
from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.test.utils import get_runner
from django.urls import include, path, set_script_prefix
from django.utils.safestring import mark_safe
from PIL import Image
from nova_slider_captcha import services
from nova_slider_captcha.conf import alternative_link
from nova_slider_captcha.forms import SliderCaptchaField, SliderCaptchaFormMixin, SliderCaptchaWidget
from nova_slider_captcha.images import make_puzzle
from nova_slider_captcha.models import Challenge

urls = ModuleType("independent_followup_urls")
urls.urlpatterns = [path("tenant/puzzle/", include("nova_slider_captcha.urls", namespace="tenant_captcha"))]
sys.modules[urls.__name__] = urls


class SurfaceTests(SimpleTestCase):
    @override_settings(ROOT_URLCONF=urls.__name__)
    def test_core_mount_does_not_expose_demo_or_create_session(self):
        client = Client()
        response = client.get("/tenant/puzzle/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["endpoints"], ["init", "challenge", "verify"])
        self.assertFalse(response.cookies)
        for suffix in ("submit", "demo"):
            self.assertEqual(client.get("/tenant/puzzle/" + suffix).status_code, 404)

    @override_settings(ROOT_URLCONF=urls.__name__)
    def test_named_mount_and_script_prefix_work_without_demo(self):
        try:
            set_script_prefix("/deployment/")
            widget = SliderCaptchaWidget(api_root="tenant_captcha:api-root")
            html = widget.render("form-2-proof", "never-render-proof")
            self.assertIn('endpoint="/deployment/tenant/puzzle/"', html)
            self.assertIn('field-name="form-2-proof"', html)
            self.assertNotIn("never-render-proof", html)
        finally:
            set_script_prefix("/")

    def test_rejects_unsafe_and_non_absolute_alternative_destinations(self):
        for value in ("javascript:alert(1)", "data:text/html,x", "https://example.com/", "//example.com/",
                      "/\\example.com/", "/%5cexample.com/", "/%2fexample.com/", "/%0a/example.com/",
                      "%2Fhelp/", "help/", " /help/", "/help\t/", "/help/%7f", "", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                alternative_link(value, "Host assistance")
        self.assertEqual(alternative_link("/help/?from=login#contact", "Host assistance")["url"],
                         "/help/?from=login#contact")

    @override_settings(NOVA_SLIDER_ALTERNATIVE_URL="/support/", NOVA_SLIDER_ALTERNATIVE_LABEL="Global support")
    def test_alternative_is_plain_text_static_markup_with_per_widget_override(self):
        first = SliderCaptchaWidget(alternative_url="/first/", alternative_label=mark_safe('<img src=x onerror="alert(1)">'))
        html = first.render("first", None)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)
        self.assertIn('href="/first/"', html)
        self.assertGreater(html.index('href="/first/"'), html.index("</nova-slider>"))
        second = SliderCaptchaWidget().render("second", None)
        self.assertIn('href="/support/"', second)
        self.assertNotIn('/first/', second)
        with override_settings(NOVA_SLIDER_ALTERNATIVE_URL=None, NOVA_SLIDER_ALTERNATIVE_LABEL=None):
            self.assertNotIn('class="nsc-alternative"', SliderCaptchaWidget().render("third", None))

    def test_field_misconfiguration_raises_early_but_mutation_still_fails_closed(self):
        for options, message in (({"required": False}, "required=True"), ({"disabled": True}, "disabled=False")):
            with self.subTest(options=options), self.assertRaisesMessage(ValueError, message):
                SliderCaptchaField(**options)
        for name, value in (("required", False), ("disabled", True)):
            field = SliderCaptchaField()
            field._captcha_managed = True
            setattr(field, name, value)
            with self.assertRaises(ValidationError):
                field.clean("synthetic-proof")

    def test_image_payloads_are_fresh_decodable_and_have_no_answer_metadata(self):
        backgrounds = set()
        for _ in range(8):
            x, y, background, piece = make_puzzle()
            self.assertTrue(60 <= x <= 263 and 24 <= y <= 95)
            backgrounds.add(background)
            for uri, size, mode in ((background, (320, 160), "RGB"), (piece, (44, 44), "RGBA")):
                image = Image.open(io.BytesIO(base64.b64decode(uri.split(",", 1)[1])))
                image.load()
                self.assertEqual(image.size, size)
                self.assertEqual(image.mode, mode)
                self.assertFalse(image.info)
                if mode == "RGBA":
                    self.assertEqual(image.getchannel("A").getextrema(), (0, 255))
        self.assertEqual(len(backgrounds), 8)


class ProtocolTests(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)
        self.csrf = self.client.get("/captcha/init").json()["csrfToken"]

    def post(self, url, data):
        return self.client.post(url, json.dumps(data), content_type="application/json", HTTP_X_CSRFTOKEN=self.csrf)

    def proof(self, purpose):
        packet = self.post("/captcha/challenge", {"purpose": purpose}).json()
        row = Challenge.objects.get(id=packet["challengeId"])
        response = self.post("/captcha/verify", {"challengeId": str(row.pk), "x": row.target_x})
        self.assertTrue(response.json()["ok"])
        return response.json()["token"], row

    def test_demo_rejects_login_proof_without_consuming_it(self):
        token, row = self.proof("login")
        self.assertEqual(self.post("/captcha-demo/submit", {"purpose": "demo", "token": token}).status_code, 403)
        row.refresh_from_db()
        self.assertFalse(row.token_consumed)
        request = RequestFactory().get("/")
        request.session = self.client.session
        self.assertTrue(services.consume(token, request, purpose="login"))

    def test_opt_in_demo_consumes_once_and_requires_csrf(self):
        page = self.client.get("/captcha-demo/")
        self.assertContains(page, 'action="/captcha-demo/submit"')
        self.assertContains(page, 'endpoint="/captcha/"')
        token, _ = self.proof("demo")
        data = {"purpose": "demo", "token": token}
        rejected = self.client.post("/captcha-demo/submit", json.dumps(data), content_type="application/json")
        self.assertEqual(rejected.status_code, 403)
        self.assertEqual(self.post("/captcha-demo/submit", data).status_code, 200)
        self.assertEqual(self.post("/captcha-demo/submit", data).status_code, 403)

    def test_runtime_field_mutation_does_not_consume_proof(self):
        class HostForm(SliderCaptchaFormMixin, forms.Form):
            proof = SliderCaptchaField()
        token, row = self.proof("demo")
        request = RequestFactory().get("/")
        request.session = self.client.session
        for name, value in (("disabled", True), ("required", False)):
            form = HostForm({"proof": token}, request=request)
            setattr(form.fields["proof"], name, value)
            self.assertFalse(form.is_valid())
            row.refresh_from_db()
            self.assertFalse(row.token_consumed)


if __name__ == "__main__":
    sys.exit(bool(get_runner(settings)(verbosity=1, interactive=False).run_tests([__name__])))
