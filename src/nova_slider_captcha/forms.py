from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.translation import get_language, gettext_lazy as _

from .services import consume


class SliderCaptchaWidget(forms.Widget):
    template_name = "nova_slider_captcha/widget.html"

    def get_context(self, name, value, attrs):
        context = super().get_context(name, "", attrs)
        context["widget"]["endpoint"] = reverse("nova_slider_captcha:challenge").rsplit("challenge", 1)[0]
        context["widget"]["locale"] = context["widget"]["attrs"].get("locale") or get_language() or "zh-hans"
        return context

    class Media:
        css = {"all": ("nova_slider_captcha/slider.css",)}
        js = ("nova_slider_captcha/slider.js",)


class SliderAdminAuthenticationForm(AdminAuthenticationForm):
    nova_slider_token = forms.CharField(label=_("Security verification"), required=True, max_length=128, widget=SliderCaptchaWidget, error_messages={"required": _("Complete the security verification before signing in.")})

    def clean(self):
        # Validate/consume before authentication so missing/invalid CAPTCHA never
        # reaches password backends. A failed password requires a fresh proof.
        token = self.cleaned_data.get("nova_slider_token")
        if not token or self.request is None or not consume(token, self.request, purpose="login"):
            raise ValidationError(_("Security verification is missing, expired, or already used. Please try again."), code="captcha_invalid")
        return super().clean()
