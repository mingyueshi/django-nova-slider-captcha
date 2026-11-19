import io
from unittest.mock import patch

from django.contrib.auth import SESSION_KEY, get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import DatabaseError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from demo.models import ProfileApproval
from demo.profile import MAX_ATTEMPTS, MEMBER_GROUP, PURPOSE
from demo.settings import NOVA_SLIDER_PURPOSES
from tests.test_captcha import CaptchaHelpers


@override_settings(NOVA_SLIDER_PURPOSES=NOVA_SLIDER_PURPOSES)
class ProfileDemoTests(CaptchaHelpers, TestCase):
    password = "local-test-profile-password"

    def setUp(self):
        self.profile = reverse("demo-profile")
        self.alternative = reverse("demo-profile-alternative")
        self.login_url = reverse("demo-profile-login")
        self.members = Group.objects.create(name=MEMBER_GROUP)
        self.user = self.make_user("reader")
        self.client = Client(enforce_csrf_checks=True)

    def make_user(self, username, *, enrolled=True, **options):
        user = get_user_model().objects.create_user(username, password=self.password, first_name="旧名称", **options)
        if enrolled:
            user.groups.add(self.members)
        return user

    def post_form(self, client, url, data, **extra):
        return client.post(url, {**data, "csrfmiddlewaretoken": client.cookies["csrftoken"].value}, **extra)

    def login(self, client, user, **extra):
        return self.post_form(client, self.login_url, {"username": user.username, "password": self.password}, **extra)

    def approve(self, reference=None):
        if reference is None:
            reference = self.client.get(self.alternative).context["reference"]
        stdout = io.StringIO()
        call_command("approve_demo_profile_change", self.user.username, reference, stdout=stdout)
        return stdout.getvalue().strip()

    def submit(self, code, *, name="新名称", client=None, **extra):
        return self.post_form(client or self.client, self.alternative, {"code": code, "display_name": name, **extra})

    def test_enrolled_ordinary_login_reaches_widget_and_alternative(self):
        self.assertRedirects(self.client.get(self.profile), f"{self.login_url}?next={self.profile}")
        self.assertRedirects(self.login(self.client, self.user), self.profile)
        self.assertEqual(self.client.session[SESSION_KEY], str(self.user.pk))
        response = self.client.get(self.profile)
        self.assertContains(response, f'purpose="{PURPOSE}"')
        self.assertContains(response, f'href="{self.alternative}"')
        response = self.client.get(self.alternative)
        self.assertContains(response, "一次性批准代码")
        self.assertNotContains(response, "<script")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertRedirects(self.client.get("/admin/"), "/admin/login/?next=/admin/")

    def test_nonmember_staff_superuser_and_inactive_accounts_get_no_session(self):
        self.client.get(self.login_url)
        roles = {
            "nonmember": {"enrolled": False},
            "staff": {"is_staff": True},
            "superuser": {"is_superuser": True, "is_staff": False},
            "inactive": {"is_active": False},
        }
        for username, options in roles.items():
            with self.subTest(username=username):
                user = self.make_user(username, **options)
                self.assertContains(self.login(self.client, user), "无法登录")
                self.assertNotIn(SESSION_KEY, self.client.session)
                self.assertRedirects(self.client.get("/admin/"), "/admin/login/?next=/admin/")
                with self.assertRaises(CommandError):
                    call_command("approve_demo_profile_change", username, "a" * 64, stdout=io.StringIO())
        self.assertFalse(ProfileApproval.objects.exists())

    @override_settings(NOVA_SLIDER_RATE_LIMITS={"issue_session": 1, "issue_ip": 3})
    @patch("nova_slider_captcha.services.timestamp_us", return_value=1_000_000)
    def test_login_limits_ip_and_session_before_authentication(self, _timestamp):
        self.client.get(self.login_url)
        for peer, expected in (("192.0.2.10", 200), ("192.0.2.11", 429)):
            with patch("django.contrib.auth.forms.authenticate", return_value=None) as authenticate:
                response = self.login(self.client, self.user, REMOTE_ADDR=peer)
            self.assertEqual(response.status_code, expected)
            self.assertEqual(authenticate.call_count, int(expected == 200))
        for _ in range(2):
            other = Client(enforce_csrf_checks=True)
            other.get(self.login_url)
            with patch("django.contrib.auth.forms.authenticate", return_value=None) as authenticate:
                self.assertEqual(self.login(other, self.user, REMOTE_ADDR="192.0.2.10").status_code, 200)
            authenticate.assert_called_once()
        another = Client(enforce_csrf_checks=True)
        another.get(self.login_url)
        with patch("django.contrib.auth.forms.authenticate") as authenticate:
            denied = self.login(another, self.user, REMOTE_ADDR="192.0.2.10")
        authenticate.assert_not_called()
        self.assertEqual(denied.status_code, 429)
        self.assertGreater(int(denied["Retry-After"]), 0)
        self.assertNotIn(SESSION_KEY, another.session)

    def test_login_csrf_and_unavailable_rate_store_do_not_authenticate(self):
        self.client.get(self.login_url)
        with patch("django.contrib.auth.forms.authenticate") as authenticate:
            self.assertEqual(self.client.post(self.login_url, {"username": "reader", "password": self.password}).status_code, 403)
            with patch("demo.profile.allow_request", side_effect=DatabaseError("private")):
                self.assertContains(self.login(self.client, self.user), "暂时无法登录", status_code=503)
        authenticate.assert_not_called()
        self.assertNotIn(SESSION_KEY, self.client.session)

    def open_alternative(self, client, user):
        client.force_login(user)
        return client.get(self.alternative)

    def test_alternative_validation_retry_then_actual_save_and_replay_rejection(self):
        self.open_alternative(self.client, self.user)
        target = self.make_user("other")
        self.assertContains(self.submit("a" * 43), "批准代码无效", status_code=403)
        self.assertFalse(ProfileApproval.objects.exists())
        code = self.approve()
        approval = ProfileApproval.objects.get(user=self.user)
        self.assertNotEqual(approval.code_hash, code)
        self.assertEqual(self.client.post(self.alternative, {"code": code, "display_name": "w"}).status_code, 403)
        self.assertEqual(self.submit(code, name="").status_code, 400)
        self.assertContains(self.submit("b" * 43), "批准代码无效", status_code=403)
        approval.refresh_from_db()
        self.assertEqual(approval.attempts, 1)
        self.assertRedirects(self.submit(code, purpose="login", user_id=target.pk), self.alternative, fetch_redirect_response=False)
        success = self.client.get(self.alternative)
        self.assertContains(success, "显示名称已更新")
        self.assertContains(success, "当前显示名称：新名称")
        self.assertNotContains(success, code)
        self.assertContains(self.submit(code, name="重放"), "批准代码无效", status_code=403)
        self.user.refresh_from_db()
        target.refresh_from_db()
        approval.refresh_from_db()
        self.assertEqual((self.user.first_name, target.first_name, approval.consumed), ("新名称", "旧名称", True))

    def test_wrong_session_account_and_expired_code_cannot_consume(self):
        initial = self.open_alternative(self.client, self.user)
        code = self.approve()
        for user in (self.user, self.make_user("other")):
            other = Client(enforce_csrf_checks=True)
            self.assertNotEqual(self.open_alternative(other, user).context["reference"], initial.context["reference"])
            self.assertEqual(self.submit(code, client=other).status_code, 403)
        approval = ProfileApproval.objects.get(user=self.user)
        self.assertEqual((approval.attempts, approval.consumed), (0, False))
        with patch("demo.profile.timezone.now", return_value=approval.expires_at):
            self.assertEqual(self.submit(code).status_code, 403)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "旧名称")

    def test_attempts_lock_approval_until_operator_issues_new_code(self):
        self.open_alternative(self.client, self.user)
        old_code = self.approve()
        for _ in range(MAX_ATTEMPTS):
            self.assertEqual(self.submit("z" * 43).status_code, 403)
        self.assertEqual(self.submit(old_code).status_code, 403)
        self.assertEqual(ProfileApproval.objects.get().attempts, MAX_ATTEMPTS)
        new_code = self.approve()
        self.assertEqual(self.submit(old_code).status_code, 403)
        self.assertEqual(self.submit(new_code).status_code, 302)

    def test_invalid_reference_rejected_and_authorization_revocation_blocks_use(self):
        self.open_alternative(self.client, self.user)
        with self.assertRaises(CommandError):
            self.approve("bogus")
        code = self.approve()
        self.user.groups.remove(self.members)
        self.assertEqual(self.client.get(self.profile).status_code, 403)
        self.assertEqual(self.submit(code).status_code, 403)
        self.assertFalse(ProfileApproval.objects.get().consumed)

    def test_business_database_failure_rolls_back_approval_and_allows_retry(self):
        self.open_alternative(self.client, self.user)
        code = self.approve()
        with patch("demo.profile.eligible_accounts") as accounts:
            account = accounts.return_value.filter.return_value
            account.exists.return_value = True
            account.update.side_effect = DatabaseError("private")
            self.assertContains(self.submit(code), "暂时无法保存", status_code=503)
        self.assertFalse(ProfileApproval.objects.get().consumed)
        self.assertEqual(self.submit(code).status_code, 302)

    def test_visual_route_requires_its_own_purpose_and_updates_same_field(self):
        self.open_alternative(self.client, self.user)
        self.client.csrf = self.client.get("/captcha/init").json()["csrfToken"]
        incorrect_proof, _ = self.token(self.client, "demo")
        posted = {"display_name": "滑块更新", "proof": incorrect_proof}
        self.assertEqual(self.post_form(self.client, self.profile, posted).status_code, 400)
        proof, row = self.token(self.client, PURPOSE)
        posted["proof"] = proof
        self.assertRedirects(self.post_form(self.client, self.profile, posted), self.profile)
        row.refresh_from_db()
        self.assertTrue(row.token_consumed)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "滑块更新")
