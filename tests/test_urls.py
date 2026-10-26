from django.test import SimpleTestCase, override_settings
from django.urls import include, path, reverse

from nova_slider_captcha import views
from nova_slider_captcha.forms import SliderCaptchaWidget

urlpatterns = [
    path("api/", include("nova_slider_captcha.urls")),
    path("site/", include(([
        path("proof/", include("nova_slider_captcha.urls", namespace="public")),
        path("preview/", include(([
            path("", views.demo, {"api_root": "site:public:api-root"}, name="index"),
            path("submit", views.submit, name="submit"),
        ], "nova_slider_captcha_demo"), namespace="preview")),
    ], "site"), namespace="site")),
]


@override_settings(ROOT_URLCONF=__name__)
class CoreURLTests(SimpleTestCase):
    def test_default_core_has_no_demo_page_or_consumer(self):
        response = self.client.get("/api/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["endpoints"], ["init", "challenge", "verify"])
        self.assertNotIn(b"captcha-demo", response.content)
        self.assertNotIn("sessionid", response.cookies)
        self.assertIn("no-store", response["Cache-Control"])
        for path in ("/api/submit", "/api/demo"):
            self.assertEqual(self.client.get(path).status_code, 404)
            self.assertEqual(self.client.post(path).status_code, 404)
        self.assertEqual(self.client.post("/api/").status_code, 405)

    def test_widget_explicit_nested_namespace_selects_the_matching_api_root(self):
        widget = SliderCaptchaWidget(api_root="site:public:api-root")
        context = widget.get_context("proof", "", {})["widget"]
        self.assertEqual(context["endpoint"], "/site/proof/")
        self.assertEqual(reverse("site:public:init"), context["endpoint"] + "init")
        self.assertEqual(SliderCaptchaWidget().get_context("proof", "", {})["widget"]["endpoint"], "/api/")

    def test_demo_can_opt_in_with_independent_namespaces_and_mounts(self):
        # A signed-cookie backend keeps this routing/render test database-free.
        with override_settings(SESSION_ENGINE="django.contrib.sessions.backends.signed_cookies"):
            response = self.client.get("/site/preview/")
        self.assertContains(response, 'endpoint="/site/proof/"')
        self.assertContains(response, 'action="/site/preview/submit"')
        self.assertEqual(self.client.get("/site/preview/submit").status_code, 405)
