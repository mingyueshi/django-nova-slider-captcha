from django.test import SimpleTestCase, override_settings
from django.urls import get_script_prefix, include, path, reverse, set_script_prefix

from nova_slider_captcha import views
from nova_slider_captcha.forms import SliderCaptchaWidget


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
