"""Host-owned example for the local, single-database demo."""
from django import forms
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.views import LoginView
from django.core.exceptions import PermissionDenied
from django.db import DatabaseError, transaction
from django.db.models import F
from django.shortcuts import redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_http_methods

from nova_slider_captcha.forms import SliderCaptchaField, SliderCaptchaFormMixin, SliderCaptchaWidget
from nova_slider_captcha.services import allow_request

from .models import ProfileApproval

MEMBER_GROUP = "profile-demo-members"
PURPOSE = "demo_profile"
APPROVAL_SECONDS = 300
MAX_ATTEMPTS = 5


def eligible_accounts():
    return get_user_model().objects.filter(
        is_active=True, is_staff=False, is_superuser=False, groups__name=MEMBER_GROUP,
    )


class DemoAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not eligible_accounts().filter(pk=user.pk).exists():
            raise self.get_invalid_login_error()


class DemoLoginView(LoginView):
    template_name = "demo/profile_login.html"
    authentication_form = DemoAuthenticationForm
    next_page = reverse_lazy("demo-profile")

    def post(self, request, *args, **kwargs):
        # Share the local demo's existing issue IP/session budget. Perform this
        # before creating a bound AuthenticationForm, including error responses.
        try:
            decision = allow_request(request, "issue")
        except (DatabaseError, ValueError):
            return self._unavailable("暂时无法登录，请稍后重试。", 503)
        if decision:
            return super().post(request, *args, **kwargs)
        response = self._unavailable("登录尝试过多，请稍后重试。", 429)
        response["Retry-After"] = str(decision.retry_after)
        return response

    def _unavailable(self, message, status):
        form = self.get_form_class()(request=self.request)
        return self.render_to_response(self.get_context_data(form=form, login_error=message), status=status)


def approval_hash(code):
    return salted_hmac("demo.profile.change_name.code", code, algorithm="sha256").hexdigest()


def session_reference(request):
    if request.session.session_key is None:
        raise PermissionDenied
    return salted_hmac("demo.profile.change_name.session", request.session.session_key, algorithm="sha256").hexdigest()


def consume_approval(user_id, reference, code):
    active = ProfileApproval.objects.filter(
        user_id=user_id, session_reference=reference, consumed=False,
        expires_at__gt=timezone.now(), attempts__lt=MAX_ATTEMPTS,
    )
    digest = approval_hash(code)
    if active.filter(code_hash=digest).update(consumed=True):
        return True
    active.exclude(code_hash=digest).update(attempts=F("attempts") + 1)
    return False


class DisplayNameForm(forms.Form):
    display_name = forms.CharField(label="新显示名称", max_length=150)


class SliderNameForm(SliderCaptchaFormMixin, DisplayNameForm):
    proof = SliderCaptchaField(purpose=PURPOSE)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["proof"].widget = SliderCaptchaWidget(
            purpose=PURPOSE, alternative_url=reverse("demo-profile-alternative"),
            alternative_label="使用非视觉验证更改显示名称",
        )


class ApprovedNameForm(DisplayNameForm):
    code = forms.RegexField(
        r"\A[A-Za-z0-9_-]{43}\Z", label="一次性批准代码", max_length=43,
        widget=forms.PasswordInput(attrs={"autocomplete": "one-time-code"}),
        error_messages={"invalid": "请输入核验人员提供的完整批准代码。"},
    )


@never_cache
@sensitive_post_parameters("code", "proof")
@login_required(login_url="demo-profile-login")
@csrf_protect
@require_http_methods(["GET", "POST"])
def change_name(request, alternative=False):
    accounts = eligible_accounts().filter(pk=request.user.pk)
    if not accounts.exists():
        raise PermissionDenied
    reference = session_reference(request) if alternative else None
    data = request.POST if request.method == "POST" else None
    form = ApprovedNameForm(data) if alternative else SliderNameForm(data, request=request)
    status = 200
    service_error = False
    if data is not None:
        saved = False
        try:
            with transaction.atomic():
                if form.is_valid():
                    if alternative and not consume_approval(request.user.pk, reference, form.cleaned_data["code"]):
                        form.add_error("code", "批准代码无效、已用或已过期。请检查代码，或联系核验人员重新批准。")
                        status = 403
                    elif accounts.update(first_name=form.cleaned_data["display_name"]) != 1:
                        # Roll back proof consumption if authorization has changed.
                        raise PermissionDenied
                    else:
                        saved = True
                else:
                    status = 400
        except DatabaseError:
            status = 503
            service_error = True
        else:
            if saved:
                messages.success(request, "显示名称已更新。")
                return redirect("demo-profile-alternative" if alternative else "demo-profile")
    return render(request, "demo/profile.html", {
        "form": form, "alternative": alternative, "reference": reference,
        "service_error": service_error,
    }, status=status)
