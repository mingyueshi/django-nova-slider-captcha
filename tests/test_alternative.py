from django import forms
from django.test import SimpleTestCase, override_settings
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy

from nova_slider_captcha.checks import captcha_settings_check
from nova_slider_captcha.forms import SliderCaptchaField, SliderCaptchaWidget


class FieldConfigurationTests(SimpleTestCase):
    def test_invalid_flags_fail_at_construction_with_developer_message(self):
        for kwargs, message in (({"required": False}, "required=True"), ({"disabled": True}, "disabled=False")):
            with self.subTest(kwargs=kwargs), self.assertRaisesMessage(ValueError, message):
                SliderCaptchaField(**kwargs)

    def test_field_rejects_a_plain_text_widget(self):
        with self.assertRaisesMessage(ValueError, "SliderCaptchaField requires SliderCaptchaWidget"):
            SliderCaptchaField(widget=forms.TextInput)


class AlternativeLinkTests(SimpleTestCase):
    def test_unconfigured_widget_does_not_claim_an_available_alternative(self):
        html = SliderCaptchaWidget().render("proof", "")
        self.assertNotIn('class="nsc-alternative"', html)
        self.assertNotIn("<a ", html)

    def test_safe_local_link_is_visible_outside_js_and_noscript_subtrees(self):
        widget = SliderCaptchaWidget(alternative_url="/security/other/?source=form&step=1", alternative_label="Use another secure method")
        html = widget.render("proof", "")
        self.assertIn('href="/security/other/?source=form&amp;step=1"', html)
        self.assertIn('Use another secure method</a>', html)
        self.assertGreater(html.index('class="nsc-alternative"'), html.index("</nova-slider>"))
        self.assertGreater(html.index('class="nsc-alternative"'), html.index("</noscript>"))

    def test_url_and_label_are_escaped_even_if_host_uses_safe_string(self):
        widget = SliderCaptchaWidget(alternative_url=mark_safe('/secure/?x="<b>'), alternative_label=mark_safe('<img src=x onerror="x">'))
        html = widget.render("proof", "")
        self.assertNotIn("<img", html)
        self.assertNotIn('href="/secure/?x="', html)
        self.assertIn("&lt;img", html)

    def test_invalid_local_urls_and_labels_are_rejected(self):
        for url in ("javascript:alert(1)", "https://evil.test/", "//evil.test/", "///evil.test/", "/\\evil.test/", "/%2fevil.test/", "/%5cevil.test/", "/%0aevil", "%2Fhelp/", " /ok/", "/a b", "/a\n", "relative/", "", None, True):
            with self.subTest(url=url), self.assertRaises(ValueError):
                SliderCaptchaWidget(alternative_url=url, alternative_label="Other")
        for label in ("", "  ", "x" * 201, "x\ny", None, True):
            with self.subTest(label=label), self.assertRaises(ValueError):
                SliderCaptchaWidget(alternative_url="/secure/", alternative_label=label)

    @override_settings(NOVA_SLIDER_ALTERNATIVE_URL="/secure/", NOVA_SLIDER_ALTERNATIVE_LABEL="Other secure route")
    def test_global_admin_friendly_configuration_is_dynamic_and_overridable(self):
        widget = SliderCaptchaWidget()
        self.assertIn('href="/secure/"', widget.render("proof", ""))
        with override_settings(NOVA_SLIDER_ALTERNATIVE_URL="/another/"):
            self.assertIn('href="/another/"', widget.render("proof", ""))
        explicit = SliderCaptchaWidget(alternative_url="/specific/", alternative_label=gettext_lazy("Specific route"))
        self.assertIn('href="/specific/"', explicit.render("proof", ""))
        with override_settings(NOVA_SLIDER_ALTERNATIVE_URL="javascript:bad"):
            self.assertIn("nova_slider_captcha.E007", [error.id for error in captcha_settings_check(None)])
            self.assertNotIn('class="nsc-alternative"', widget.render("proof", ""))

    def test_multiple_prefixed_widgets_keep_distinct_links_and_field_names(self):
        class Proofs(forms.Form):
            first = SliderCaptchaField(widget=SliderCaptchaWidget(alternative_url="/secure/one/", alternative_label="First"))
            second = SliderCaptchaField(widget=SliderCaptchaWidget(alternative_url="/secure/two/", alternative_label="Second"))
        html = Proofs(prefix="form-1").as_p()
        self.assertEqual(html.count('class="nsc-alternative"'), 2)
        for name, url in (("first", "one"), ("second", "two")):
            self.assertIn(f'field-name="form-1-{name}"', html)
            self.assertIn(f'href="/secure/{url}/"', html)
