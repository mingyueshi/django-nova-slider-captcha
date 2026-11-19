import io
import json
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch

from django.apps import apps
from django.conf import settings
from django.contrib.admin import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management import call_command
from django.db import connections
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import NoReverseMatch, path, reverse
from django.utils import timezone, translation

from demo.profile import DemoAdminAuthenticationForm
from demo.urls import admin_site as demo_admin, urlpatterns as demo_urls
from nova_slider_captcha.admin import SliderCaptchaAdminSite
from nova_slider_captcha.models import RateBucket, RateLimitState
from nova_slider_captcha.services import timestamp_us
from tests.test_boundaries import CaptchaReplicaRouter


stats_admin = SliderCaptchaAdminSite(name="stats-admin")
ordinary_admin = AdminSite(name="ordinary-admin")
urlpatterns = [*demo_urls, path("stats/", stats_admin.urls), path("ordinary/", ordinary_admin.urls)]


@override_settings(DATABASE_ROUTERS=[CaptchaReplicaRouter()])
class RateStatsTests(TestCase):
    databases = {"default", "captcha", "replica"}

    def run_stats(self, now, *, as_json):
        output = io.StringIO()
        with (
            patch("nova_slider_captcha.rate_stats.current_time",
                  return_value=now) as clock,
            CaptureQueriesContext(connections["captcha"]) as writer,
            CaptureQueriesContext(connections["replica"]) as replica,
            CaptureQueriesContext(connections["default"]) as default,
        ):
            call_command("slider_captcha_rate_stats", stdout=output, json=as_json)
        clock.assert_called_once_with()
        self.assertEqual(len(writer), 2)
        self.assertTrue(all(query["sql"].lstrip().upper().startswith("SELECT ") for query in writer))
        self.assertEqual(len(replica), 0)
        self.assertEqual(len(default), 0)
        return output.getvalue()

    def test_empty_database_has_stable_zero_groups(self):
        now = timezone.now()
        result = json.loads(self.run_stats(now, as_json=True))
        self.assertEqual(result["sampled_at"], now.isoformat())
        self.assertEqual(result["legacy"], {"total": 0, "prunable": 0})
        self.assertEqual([(row["action"], row["scope"]) for row in result["states"]],
                         [("init", "ip"), ("issue", "session"), ("issue", "ip"),
                          ("verify", "session"), ("verify", "ip"), ("other", "other")])
        for row in result["states"]:
            self.assertEqual([row[key] for key in ("total", "debt", "cooldown", "prunable")], [0] * 4)

    def test_boundaries_overlap_privacy_and_format_agreement(self):
        now = timezone.now()
        current = timestamp_us(now)
        buckets = RateLimitState.objects.using("captcha")
        for subject, debt, cooldown in (("a", 0, 0), ("b", 1, 0), ("c", 0, 1), ("d", 1, 1)):
            buckets.create(key="issue:ip:" + subject * 64, tat_us=current + debt,
                           blocked_until_us=current + cooldown)
        private_keys = ["unknown:ip:" + "e" * 64, "issue:ip:malformed-private", "legacy-private"]
        for key in private_keys[:2]:
            buckets.create(key=key, tat_us=current, blocked_until_us=current)
        RateLimitState.objects.using("replica").create(key="verify:ip:" + "f" * 64)
        for offset in (-1, 0, 1):
            RateBucket.objects.using("captcha").create(
                key=f"{private_keys[2]}-{offset}", expires_at=now + timedelta(microseconds=offset),
            )

        raw = self.run_stats(now, as_json=True)
        plain = self.run_stats(now, as_json=False)
        result = json.loads(raw)
        self.assertEqual(result["states"][2],
                         {"action": "issue", "scope": "ip", "total": 4, "debt": 2, "cooldown": 2, "prunable": 1})
        self.assertEqual(result["states"][-1],
                         {"action": "other", "scope": "other", "total": 2, "debt": 0, "cooldown": 0, "prunable": 2})
        self.assertEqual(sum(row["total"] for row in result["states"]), 6)
        self.assertEqual(result["legacy"], {"total": 3, "prunable": 1})
        for row in result["states"]:
            self.assertIn(" ".join(str(row[k]) for k in ("action", "scope", "total", "debt", "cooldown", "prunable")),
                          plain.splitlines())
        self.assertIn("遗留 RateBucket total=3 prunable=1", plain.splitlines())
        self.assertIn("债务与冷却可能重叠", plain)
        self.assertIn("存量统计无法还原历史 429", plain)
        for private in (*private_keys, "a" * 64, "b" * 64, "c" * 64, "d" * 64):
            self.assertNotIn(private, raw + plain)


@override_settings(ROOT_URLCONF=__name__, DATABASE_ROUTERS=[CaptchaReplicaRouter()])
class AdminRateStatsTests(TestCase):
    databases = {"default", "captcha", "replica"}

    def setUp(self):
        self.url = reverse("stats-admin:nova_slider_rate_stats")
        self.index = reverse("stats-admin:index")
        self.user = get_user_model().objects.create_user(username="operator", is_staff=True)

    def grant(self, *permissions):
        for codename in permissions:
            self.user.user_permissions.add(Permission.objects.get(
                content_type__app_label="nova_slider_captcha", codename=codename,
            ))

    def test_only_opt_in_site_has_the_route_and_keeps_its_registry(self):
        with self.assertRaises(NoReverseMatch):
            reverse("ordinary-admin:nova_slider_rate_stats")
        for site in (stats_admin, ordinary_admin):
            self.assertFalse(site.is_registered(RateLimitState))
            self.assertFalse(site.is_registered(RateBucket))
        self.assertTrue(demo_admin.is_registered(get_user_model()))
        self.assertIs(demo_admin.login_form, DemoAdminAuthenticationForm)

    def test_anonymous_inactive_nonstaff_and_partial_permissions_are_denied(self):
        with patch("nova_slider_captcha.admin.rate_stats") as stats:
            self.assertRedirects(self.client.get(self.url), reverse("stats-admin:login") + "?next=" + self.url)
            self.grant("view_ratelimitstate")
            self.client.force_login(self.user)
            self.assertNotContains(self.client.get(self.index), self.url)
            self.assertEqual(self.client.get(self.url).status_code, 403)
            self.grant("view_ratebucket")
            self.user.is_active = False
            self.user.save(update_fields=["is_active"])
            self.assertEqual(self.client.get(self.url).status_code, 302)
            self.user.is_active = True
            self.user.is_staff = False
            self.user.save(update_fields=["is_active", "is_staff"])
            self.assertEqual(self.client.get(self.url).status_code, 302)
        stats.assert_not_called()

    def test_authorized_page_matches_command_and_uses_writer_only(self):
        self.grant("view_ratelimitstate", "view_ratebucket")
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self.index), self.url)
        now = timezone.now()
        secret = "a" * 64
        RateLimitState.objects.using("captcha").create(key=f"issue:session:{secret}", tat_us=timestamp_us(now) + 1)
        RateLimitState.objects.using("replica").create(key=f"issue:session:{'b' * 64}")
        RateBucket.objects.using("captcha").create(key="private-legacy", expires_at=now - timedelta(microseconds=1))
        output = io.StringIO()
        with patch("nova_slider_captcha.rate_stats.current_time", return_value=now) as clock:
            with (
                CaptureQueriesContext(connections["captcha"]) as writer,
                CaptureQueriesContext(connections["replica"]) as replica,
            ):
                response = self.client.get(self.url)
            clock.assert_called_once_with()
            call_command("slider_captcha_rate_stats", stdout=output, json=True)
        self.assertEqual(len(writer), 2)
        self.assertTrue(all(query["sql"].lstrip().upper().startswith("SELECT ") for query in writer))
        self.assertEqual(len(replica), 0)
        self.assertEqual(response.context["stats"], json.loads(output.getvalue()))
        self.assertEqual(response.context["stats"]["states"][1]["debt"], 1)
        self.assertNotContains(response, secret)
        self.assertNotContains(response, "private-legacy")
        self.assertContains(response, self.index)
        self.assertContains(response, '<th scope="col">')
        self.assertIn("no-store", response["Cache-Control"])

    def test_page_and_index_follow_admin_language_and_namespace(self):
        self.grant("view_ratelimitstate", "view_ratebucket")
        self.client.force_login(self.user)
        for language, title, label in (
            ("en", "CAPTCHA rate statistics", "View CAPTCHA rate statistics"),
            ("zh-hans", "验证码限流统计", "查看验证码限流统计"),
        ):
            with self.subTest(language=language), translation.override(language):
                index = self.client.get(self.index)
                self.assertContains(index, f'<a href="{self.url}">{label}</a>', html=True)
                page = self.client.get(self.url)
                self.assertContains(page, title)
                self.assertContains(page, f'<a href="{self.index}">{"Home" if language == "en" else "首页"}</a>', html=True)
                self.assertNotContains(page, translation.gettext("You don’t have permission to view or edit anything."))
                self.assertContains(page, f'<a href="{self.url}" aria-current="page">{label}</a>', html=True)
                self.assertEqual(page.context["available_apps"], [])

    def test_index_empty_notice_only_applies_without_statistics_access(self):
        notice = "You don’t have permission to view or edit anything."
        self.client.force_login(self.user)
        with translation.override("en"):
            self.assertContains(self.client.get(self.index), notice)
            self.grant("view_ratelimitstate", "view_ratebucket")
            index = self.client.get(self.index)
            self.assertContains(index, self.url)
            self.assertContains(index, f'<a href="{self.url}" class="viewlink" '
                                       'aria-describedby="nova-slider-operations-ratestatistics">View</a>', html=True)
            self.assertNotContains(index, 'class="addlink"')
            self.assertNotContains(index, 'class="changelink"')
            self.assertEqual(index.context["app_list"], [])
            self.assertEqual(index.context["nova_rate_stats_url"], self.url)
            self.assertNotContains(index, notice)
            self.assertContains(index, "Recent actions")
            if apps.is_installed("nova_admin"):
                native_context = stats_admin.each_context
                with patch.object(stats_admin, "each_context", side_effect=lambda request: {
                    **native_context(request),
                    "nova_kpis": [{"label": "Temporary metric", "value": 42}],
                }):
                    nova_index = self.client.get(self.index)
                self.assertContains(nova_index, "Temporary metric")
                self.assertNotContains(nova_index, notice)

            self.user.user_permissions.add(Permission.objects.get(
                content_type__app_label="auth", codename="view_user",
            ))
            demo_index = self.client.get(reverse("admin:index"))
            self.assertContains(demo_index, reverse("admin:nova_slider_rate_stats"))
            self.assertContains(demo_index, reverse("admin:auth_user_changelist"))
            self.assertContains(self.client.get(reverse("admin:nova_slider_rate_stats")),
                                reverse("admin:auth_user_changelist"))

    def test_statistics_preserve_custom_sidebar_with_no_models(self):
        self.grant("view_ratelimitstate", "view_ratebucket")
        self.client.force_login(self.user)
        templates = deepcopy(settings.TEMPLATES)
        templates[0]["APP_DIRS"] = False
        templates[0]["OPTIONS"]["loaders"] = [
            ("django.template.loaders.locmem.Loader", {
                "admin/nav_sidebar.html": '<nav aria-label="Host tools"><a href="/host/">Host navigation</a></nav>',
            }),
            "django.template.loaders.app_directories.Loader",
        ]
        with self.settings(TEMPLATES=templates):
            response = self.client.get(self.url)
        self.assertContains(response, '<nav aria-label="Host tools"><a href="/host/">Host navigation</a></nav>', html=True)

    def test_statistics_enforce_staff_and_site_permission_independently(self):
        self.grant("view_ratelimitstate", "view_ratebucket")
        self.client.force_login(self.user)
        with patch("nova_slider_captcha.admin.rate_stats") as stats:
            with patch.object(stats_admin, "has_permission", return_value=True):
                self.user.is_staff = False
                self.user.save(update_fields=["is_staff"])
                self.assertNotContains(self.client.get(self.index), self.url)
                self.assertEqual(self.client.get(self.url).status_code, 403)
                self.user.is_staff = True
                self.user.is_active = False
                self.user.save(update_fields=["is_staff", "is_active"])
                self.assertEqual(self.client.get(self.url).status_code, 403)
            self.user.is_active = True
            self.user.save(update_fields=["is_active"])
            with patch.object(stats_admin, "has_permission", return_value=False):
                self.assertEqual(self.client.get(self.index).status_code, 302)
                self.assertEqual(self.client.get(self.url).status_code, 302)
            stats.assert_not_called()

    def test_superuser_has_access_but_mutating_methods_do_not_aggregate(self):
        self.user.is_superuser = True
        self.user.save(update_fields=["is_superuser"])
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self.index), self.url)
        with patch("nova_slider_captcha.admin.rate_stats") as stats:
            response = self.client.post(self.url)
            self.assertEqual(response.status_code, 405)
            self.assertEqual(response["Allow"], "GET, HEAD")
            stats.assert_not_called()
        response = self.client.head(self.url)
        self.assertEqual((response.status_code, response.content), (200, b""))
