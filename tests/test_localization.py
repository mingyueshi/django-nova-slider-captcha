"""Django localization contract; no browser or external service is required."""
from django.template.loader import render_to_string
from django.test import SimpleTestCase
from django.utils.translation import gettext, override

from nova_slider_captcha.forms import SliderAdminAuthenticationForm, SliderCaptchaWidget


class LocalizationTests(SimpleTestCase):
    def test_simplified_chinese_catalog_translates_form_labels_and_errors(self):
        with override("zh-hans"):
            field = SliderAdminAuthenticationForm.base_fields["nova_slider_token"]
            self.assertEqual(str(field.label), "安全验证")
            self.assertEqual(str(field.error_messages["required"]), "请先完成安全验证，再登录。")
            self.assertEqual(
                gettext("Security verification is missing, expired, or already used. Please try again."),
                "安全验证缺失、已过期或已使用，请重新验证。",
            )

    def test_english_form_labels_and_errors_remain_english(self):
        with override("en"):
            field = SliderAdminAuthenticationForm.base_fields["nova_slider_token"]
            self.assertEqual(str(field.label), "Security verification")
            self.assertEqual(str(field.error_messages["required"]), "Complete the security verification before signing in.")

    def test_widget_inherits_active_django_locale_and_translates_noscript(self):
        for locale, label, instruction in [
            ("en", "Security verification", "JavaScript is required"),
            ("zh-hans", "安全验证", "此图形验证需要 JavaScript"),
        ]:
            with self.subTest(locale=locale), override(locale):
                html = SliderCaptchaWidget().render("nova_slider_token", "never-render-this-proof", attrs={"id": "id_proof"})
                self.assertIn(f'locale="{locale}"', html)
                self.assertIn(f'aria-label="{label}"', html)
                self.assertIn(instruction, html)
                self.assertNotIn("never-render-this-proof", html)
                self.assertEqual(html.count('id="id_proof"'), 1)

    def test_explicit_widget_locale_overrides_active_language_and_is_escaped(self):
        with override("zh-hans"):
            html = SliderCaptchaWidget(attrs={"locale": "en-GB"}).render("nova_slider_token", None)
            self.assertIn('locale="en-GB"', html)
            self.assertNotIn('id=""', html)
            html = SliderCaptchaWidget(attrs={"locale": '\"><script>alert(1)</script>'}).render("nova_slider_token", None)
            self.assertNotIn("<script>", html)
            self.assertIn("&lt;script&gt;", html)

    def test_demo_template_localizes_all_display_text_and_explicit_locale(self):
        for locale, submit, title in [
            ("en", "Submit protected request", "Django demo"),
            ("zh-hans", "提交受保护的请求", "Django 演示"),
        ]:
            with self.subTest(locale=locale), override(locale):
                html = render_to_string("nova_slider_captcha/demo.html")
                self.assertIn(f'<html lang="{locale}">', html)
                self.assertIn(f'locale="{locale}"', html)
                self.assertIn(submit, html)
                self.assertIn(title, html)
