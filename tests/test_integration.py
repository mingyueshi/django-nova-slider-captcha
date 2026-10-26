import base64
import io
from unittest.mock import patch

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import DatabaseError
from django.forms import formset_factory
from django.test import TestCase, override_settings
from PIL import Image

from nova_slider_captcha import services
from nova_slider_captcha.checks import captcha_settings_check
from nova_slider_captcha.conf import purposes
from nova_slider_captcha.forms import SliderCaptchaField, SliderCaptchaFormMixin
from nova_slider_captcha.models import Challenge, RateLimitState
from tests.test_captcha import CaptchaHelpers


class ContactForm(SliderCaptchaFormMixin, forms.Form):
    email = forms.EmailField()
    proof = SliderCaptchaField(purpose="contact")

    def clean(self):
        data = super().clean()
        if data.get("email") == "blocked@example.com":
            raise ValidationError("Business rejection")
        return data


class UserForm(SliderCaptchaFormMixin, forms.ModelForm):
    proof = SliderCaptchaField(purpose="contact")

    class Meta:
        model = get_user_model()
        fields = ["username", "email"]


@override_settings(NOVA_SLIDER_PURPOSES=["demo", "login", "contact", "other"])
class FormIntegrationTests(CaptchaHelpers, TestCase):
    def setUp(self):
        self.client = self.client_with_init()
        self.req = self.request(self.client)
        self.proof, self.row = self.token(self.client, "contact")

    def form(self, **kwargs):
        return ContactForm(data=kwargs.pop("data", {"email": "ok@example.com", "proof": self.proof}), request=kwargs.pop("request", self.req), **kwargs)

    def consumed(self):
        self.row.refresh_from_db()
        return self.row.token_consumed

    def test_consume_only_after_field_and_form_validation(self):
        for email in ("invalid", "blocked@example.com"):
            self.assertFalse(self.form(data={"email": email, "proof": self.proof}).is_valid())
            self.assertFalse(self.consumed())
        self.assertTrue(self.form().is_valid())
        self.assertTrue(self.consumed())

    def test_model_validation_failure_preserves_proof_and_valid_model_can_save(self):
        get_user_model().objects.create(username="taken")
        form = UserForm({"username": "taken", "proof": self.proof}, request=self.req)
        self.assertFalse(form.is_valid())
        self.assertIn("username", form.errors)
        self.assertFalse(self.consumed())
        form = UserForm({"username": "new", "proof": self.proof}, request=self.req)
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.save().username, "new")
        self.assertTrue(self.consumed())

    def test_model_clean_and_constraint_failures_preserve_proof(self):
        for method in ("clean", "validate_constraints"):
            with patch.object(get_user_model(), method, side_effect=ValidationError("model rejected")):
                form = UserForm({"username": "new", "proof": self.proof}, request=self.req)
                self.assertFalse(form.is_valid())
                self.assertFalse(self.consumed())

    def test_repeated_is_valid_and_full_clean_consume_once(self):
        form = self.form()
        with patch("nova_slider_captcha.forms.consume", wraps=services.consume) as consume:
            self.assertTrue(form.is_valid())
            self.assertTrue(form.is_valid())
            form.full_clean()
            self.assertTrue(form.is_valid(), form.errors)
            self.assertEqual(consume.call_count, 1)
        self.assertFalse(self.form().is_valid())

    def test_context_change_permanently_invalidates_successful_instance(self):
        form = self.form()
        self.assertTrue(form.is_valid())
        form.data["proof"] = "x" * 43
        self.assertFalse(form.is_valid())
        form.data["proof"] = self.proof
        form.full_clean()
        self.assertFalse(form.is_valid())

    def test_changed_cleaned_token_cannot_reuse_cached_consumption(self):
        for method in ("cleaned_data", "clean_proof"):
            token, _ = self.token(self.client, "contact")
            form = self.form(data={"email": "ok@example.com", "proof": token})
            self.assertTrue(form.is_valid())
            second, row = self.token(self.client, "contact")
            if method == "cleaned_data":
                form.cleaned_data["proof"] = second
            else:
                form.clean_proof = lambda: second
                form.full_clean()
            self.assertFalse(form.is_valid())
            row.refresh_from_db()
            self.assertFalse(row.token_consumed)

    def test_cached_success_cannot_change_token_request_purpose_or_binding(self):
        for change in ("token", "request", "purpose", "binding", "disabled", "required", "removed"):
            token, row = self.token(self.client, "contact")
            request = self.request(self.client)
            form = self.form(data={"email": "ok@example.com", "proof": token}, request=request)
            self.assertTrue(form.is_valid())
            if change == "token":
                form.data["proof"] = "x" * 43
            elif change == "request":
                form.request = self.request(self.client)
            elif change == "purpose":
                form.fields["proof"].purpose = "other"
            elif change == "binding":
                request.session["_nova_slider_binding"] = "different"
            elif change == "removed":
                del form.fields["proof"]
            else:
                setattr(form.fields["proof"], change, change == "disabled")
            self.assertFalse(form.is_valid(), change)
            form.full_clean()
            self.assertFalse(form.is_valid(), change)

    def test_missing_request_or_mixin_and_wrong_session_or_purpose_fail_closed(self):
        for request in (None, self.request(self.client_with_init())):
            self.assertFalse(self.form(request=request).is_valid())
        plain = type("Plain", (forms.Form,), {"proof": SliderCaptchaField(purpose="contact")})
        self.assertFalse(plain({"proof": self.proof}).is_valid())
        form = self.form()
        form.fields["proof"].purpose = "other"
        self.assertFalse(form.is_valid())
        self.assertFalse(self.consumed())

    def test_prefixed_custom_field_widget_and_formset_names(self):
        form = self.form(data={"a-email": "ok@example.com", "a-proof": self.proof}, prefix="a")
        self.assertIn('field-name="a-proof"', str(form["proof"]))
        self.assertIn('purpose="contact"', str(form["proof"]))
        self.assertNotIn(self.proof, str(form["proof"]))
        self.assertTrue(form.is_valid())
        token, _ = self.token(self.client, "contact")
        FormSet = formset_factory(ContactForm, extra=0)
        formset = FormSet({"form-TOTAL_FORMS": "1", "form-INITIAL_FORMS": "0", "form-0-email": "ok@example.com", "form-0-proof": token}, form_kwargs={"request": self.req})
        self.assertIn('field-name="form-0-proof"', str(formset.forms[0]["proof"]))
        self.assertTrue(formset.is_valid(), formset.errors)

    def test_multiple_fields_commit_together_and_duplicate_token_rolls_back(self):
        class Multi(SliderCaptchaFormMixin, forms.Form):
            first = SliderCaptchaField(purpose="contact")
            second = SliderCaptchaField(purpose="other")
        form = Multi({"first": self.proof, "second": "x" * 43}, request=self.req)
        self.assertFalse(form.is_valid())
        self.assertFalse(self.consumed())
        second, row = self.token(self.client, "other")
        form = Multi({"first": self.proof, "second": second}, request=self.req)
        self.assertIn('field-name="second"', str(form["second"]))
        self.assertTrue(form.is_valid())
        self.assertTrue(self.consumed())
        row.refresh_from_db()
        self.assertTrue(row.token_consumed)
        Multi.base_fields["second"].purpose = "contact"
        token, row = self.token(self.client, "contact")
        self.assertFalse(Multi({"first": token, "second": token}, request=self.req).is_valid())
        row.refresh_from_db()
        self.assertFalse(row.token_consumed)

    def test_formset_untouched_extra_is_ignored_without_error_or_consumption(self):
        FormSet = formset_factory(ContactForm, extra=1)
        formset = FormSet({"form-TOTAL_FORMS": "2", "form-INITIAL_FORMS": "0", "form-0-email": "ok@example.com", "form-0-proof": self.proof}, form_kwargs={"request": self.req})
        with patch("nova_slider_captcha.forms.consume", wraps=services.consume) as consume:
            self.assertTrue(formset.is_valid(), formset.errors)
            self.assertEqual(formset.forms[1].errors, {})
            self.assertEqual(formset.forms[1].cleaned_data, {})
            self.assertEqual(consume.call_count, 1)
        self.assertTrue(self.consumed())

    def test_database_error_fails_form_closed(self):
        with patch("nova_slider_captcha.forms.consume", side_effect=DatabaseError("secret")):
            self.assertFalse(self.form().is_valid())
        self.assertFalse(self.consumed())

    def test_disabling_purpose_invalidates_cached_form(self):
        form = self.form()
        self.assertTrue(form.is_valid())
        with override_settings(NOVA_SLIDER_PURPOSES=["demo"]):
            self.assertFalse(form.is_valid())


class PurposeTests(CaptchaHelpers, TestCase):
    def setUp(self):
        self.client = self.client_with_init()

    def test_defaults_and_dynamic_replacement(self):
        self.assertEqual(purposes(), {"demo", "login"})
        with override_settings(NOVA_SLIDER_PURPOSES=["contact"]):
            token, _ = self.token(self.client, "contact")
            self.assertEqual(self.post(self.client, "challenge", {"purpose": "demo"}).status_code, 400)
            self.assertFalse(services.consume(token, self.request(self.client), "demo"))
            self.assertTrue(services.consume(token, self.request(self.client), "contact"))
        self.assertEqual(purposes(), {"demo", "login"})

    def test_invalid_settings_fail_checks_services_and_http_closed(self):
        for value in ("login", {}, None, [], (), set(), [""], [1], [True], ["A"], ["a b"], ["x" * 33], ["a\n"]):
            with self.subTest(value=value), override_settings(NOVA_SLIDER_PURPOSES=value):
                self.assertIn("nova_slider_captcha.E004", [e.id for e in captcha_settings_check(None)])
                with self.assertRaises(ValueError):
                    services.issue(self.request(self.client), "demo")
                self.assertFalse(services.consume("x" * 43, self.request(self.client), "demo"))
                for endpoint, data in (("challenge", {"purpose": "demo"}), ("verify", {}), ("submit", {"purpose": "demo"})):
                    self.assertEqual(self.post(self.client, endpoint, data).status_code, 503)
        self.assertEqual(Challenge.objects.count(), 0)

    def test_collection_types_and_maximum_name(self):
        for value in (["a"], ("a",), {"a"}, frozenset(["a"])):
            with override_settings(NOVA_SLIDER_PURPOSES=value):
                self.assertEqual(purposes(), {"a"})
        with override_settings(NOVA_SLIDER_PURPOSES=["x" * 32]):
            self.challenge(self.client, "x" * 32)

    @override_settings(NOVA_SLIDER_PURPOSES=["demo", "login", "contact"], NOVA_SLIDER_RATE_LIMITS={"issue_session": 2})
    def test_new_purposes_share_action_session_and_ip_capacity(self):
        self.challenge(self.client, "contact")
        self.challenge(self.client, "demo")
        self.assertEqual(self.post(self.client, "challenge", {"purpose": "login"}).status_code, 429)
        self.assertEqual(RateLimitState.objects.count(), 2)

    def test_removed_purpose_cannot_verify_or_consume(self):
        token, row = self.token(self.client, "login")
        challenge, unsolved = self.challenge(self.client, "login")
        with override_settings(NOVA_SLIDER_PURPOSES=["demo"]):
            self.assertFalse(services.consume(token, self.request(self.client), "login"))
            self.assertFalse(services.verify(self.request(self.client), unsolved.pk, unsolved.target_x)["ok"])
        self.assertTrue(services.consume(token, self.request(self.client), "login"))

    def test_challenge_geometry_uses_shared_constants(self):
        geometry = {"WIDTH": 400, "HEIGHT": 200, "PIECE_SIZE": 50}
        with patch.multiple("nova_slider_captcha.services", **geometry), patch.multiple("nova_slider_captcha.images", **geometry):
            data = services.issue(self.request(self.client), "demo")
        self.assertEqual((data["width"], data["height"], data["pieceWidth"]), (400, 200, 50))
        for name, size in (("background", (400, 200)), ("piece", (50, 50))):
            self.assertEqual(Image.open(io.BytesIO(base64.b64decode(data[name].split(",")[1]))).size, size)

    @override_settings(NOVA_SLIDER_PURPOSES=["demo", "contact"])
    def test_demo_submission_cannot_be_repurposed_by_client(self):
        token, _ = self.token(self.client, "contact")
        self.assertEqual(self.post(self.client, "submit", {"token": token, "purpose": "contact"}).status_code, 400)
        self.assertEqual(self.post(self.client, "submit", {"token": token, "purpose": "demo"}).status_code, 403)
        self.assertTrue(services.consume(token, self.request(self.client), "contact"))

    @override_settings(NOVA_SLIDER_PURPOSES=["demo", "contact"], NOVA_SLIDER_RATE_LIMITS={"issue_ip": 2})
    def test_custom_purpose_does_not_reset_ip_budget_for_new_sessions(self):
        self.challenge(self.client, "demo")
        self.challenge(self.client_with_init(), "contact")
        self.assertEqual(self.post(self.client_with_init(), "challenge", {"purpose": "contact"}).status_code, 429)
