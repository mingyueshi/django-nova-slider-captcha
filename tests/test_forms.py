from html.parser import HTMLParser

from django import forms
from django.test import SimpleTestCase, override_settings
from django.urls import get_script_prefix, include, path, reverse, set_script_prefix

from nova_slider_captcha import views
from nova_slider_captcha.forms import SliderCaptchaField, SliderCaptchaFormMixin, SliderCaptchaWidget


# Deliberately use a different challenge path: the endpoint belongs to the root.
urlpatterns = [path("mounted/challenge-prefix/", include(([
    path("", views.api_root, name="api-root"),
    path("puzzle", views.challenge, name="challenge"),
], "nova_slider_captcha")))]


class WidgetEndpointTests(SimpleTestCase):
    def test_default_endpoint_uses_existing_root_route(self):
        endpoint = SliderCaptchaWidget().get_context("proof", "", {})["widget"]["endpoint"]
        self.assertEqual(endpoint, reverse("nova_slider_captcha:api-root"))
        self.assertEqual(endpoint, "/captcha/")

    @override_settings(ROOT_URLCONF=__name__)
    def test_mount_and_script_prefix_are_preserved_independent_of_challenge_path(self):
        previous = get_script_prefix()
        try:
            for script in ("/", "/deployment/"):
                set_script_prefix(script)
                endpoint = SliderCaptchaWidget().get_context("proof", "", {})["widget"]["endpoint"]
                self.assertEqual(endpoint, script + "mounted/challenge-prefix/")
                self.assertEqual(reverse("nova_slider_captcha:challenge"), endpoint + "puzzle")
                self.assertIn(f'endpoint="{endpoint}"', SliderCaptchaWidget().render("proof", None))
        finally:
            set_script_prefix(previous)


class WidgetMarkup(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.widgets = []
        self.ids = set()
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "nova-slider":
            self.widgets.append(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])


class WidgetAriaTests(SimpleTestCase):
    def test_form_preserves_help_and_error_references_for_each_prefixed_field(self):
        class Protected(SliderCaptchaFormMixin, forms.Form):
            proof = SliderCaptchaField()
            second = SliderCaptchaField()

        for help_text in ("", "Use the secure alternative if needed."):
            for bound in (False, True):
                with self.subTest(help=bool(help_text), bound=bound):
                    form = Protected(data={} if bound else None, prefix="account")
                    for field in form.fields.values():
                        field.help_text = help_text
                    markup = WidgetMarkup(str(form.as_p()))
                    self.assertEqual(len(markup.widgets), 2)
                    for attrs, name in zip(markup.widgets, ("proof", "second")):
                        field_id = f"id_account-{name}"
                        expected = []
                        if help_text:
                            expected.append(field_id + "_helptext")
                        if bound:
                            expected.append(field_id + "_error")
                        self.assertEqual(attrs.get("aria-describedby", "").split(), expected)
                        self.assertEqual(attrs.get("aria-invalid"), "true" if bound else None)
                        self.assertTrue(set(expected) <= markup.ids)
                        self.assertEqual(attrs["field-name"], "account-" + name)

    def test_only_supported_aria_attrs_are_forwarded_and_escaped(self):
        attrs = {"aria-describedby": 'help" onfocus="bad', "aria-invalid": "false",
                 "onclick": "bad()", "data-untrusted": "bad", "aria-owns": "other"}
        markup = WidgetMarkup(SliderCaptchaWidget(attrs=attrs).render("proof", None))
        widget = markup.widgets[0]
        self.assertEqual(widget["aria-describedby"], attrs["aria-describedby"])
        self.assertEqual(widget["aria-invalid"], "false")
        for name in ("onclick", "data-untrusted", "aria-owns", "onfocus"):
            self.assertNotIn(name, widget)
