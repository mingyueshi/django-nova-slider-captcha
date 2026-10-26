from django import forms
from django.contrib.admin.forms import AdminAuthenticationForm
from django.core.exceptions import ValidationError
from django.db import DatabaseError, router, transaction
from django.urls import reverse
from django.utils.translation import get_language, gettext_lazy as _

from .conf import alternative_link, challenge_policy, configured_alternative_link, purposes, valid_purpose
from .events import optional_link_invalid
from .models import Challenge
from .services import consume, session_binding

CAPTCHA_ERROR = _("Security verification is missing, expired, or already used. Please try again.")


class SliderCaptchaWidget(forms.Widget):
    template_name = "nova_slider_captcha/widget.html"

    def __init__(self, attrs=None, *, purpose="login", api_root="nova_slider_captcha:api-root",
                 alternative_url=None, alternative_label=None):
        super().__init__(attrs)
        self.purpose = purpose
        self.api_root = api_root
        self.alternative = alternative_link(alternative_url, alternative_label)

    def get_context(self, name, value, attrs):
        context = super().get_context(name, "", attrs)
        context["widget"]["endpoint"] = reverse(self.api_root)
        context["widget"]["locale"] = context["widget"]["attrs"].get("locale") or get_language() or "zh-hans"
        context["widget"]["purpose"] = self.purpose
        alternative = self.alternative
        if alternative is None:
            try:
                alternative = configured_alternative_link()
            except ValueError:
                # Only the optional global navigation setting degrades. E007
                # still rejects it in checks; proof/policy validation is intact.
                optional_link_invalid()
        context["widget"]["alternative"] = alternative
        return context

    class Media:
        css = {"all": ("nova_slider_captcha/slider.css",)}
        js = ("nova_slider_captcha/slider.js",)


class SliderCaptchaField(forms.CharField):
    """Syntax only here; SliderCaptchaFormMixin consumes after all validation."""

    def __init__(self, *, purpose="demo", **kwargs):
        self.purpose = purpose
        kwargs.setdefault("label", _("Security verification"))
        kwargs.setdefault("max_length", 128)
        kwargs.setdefault("widget", SliderCaptchaWidget(purpose=purpose))
        super().__init__(**kwargs)
        if not self.required:
            raise ValueError("SliderCaptchaField requires required=True; optional CAPTCHA fields are unsupported")
        if self.disabled:
            raise ValueError("SliderCaptchaField requires disabled=False; disabled CAPTCHA fields are unsupported")
        if not isinstance(self.widget, SliderCaptchaWidget):
            raise ValueError("SliderCaptchaField requires SliderCaptchaWidget")
        self.widget.purpose = purpose

    def clean(self, value):
        try:
            supported = valid_purpose(self.purpose)
        except ValueError:
            supported = False
        if not supported or self.disabled or not self.required or not getattr(self, "_captcha_managed", False):
            raise ValidationError(CAPTCHA_ERROR, code="captcha_invalid")
        return super().clean(value)


class SliderCaptchaFormMixin:
    """Put before Form/ModelForm. One instance belongs to one proof context.

    Consumption runs after _post_clean (including model uniqueness/constraints),
    before a caller performs the protected operation. Multiple CAPTCHA fields
    commit together on the Challenge write database. Business writes/save() are
    separate; a later failure needs a fresh proof. Do not use this for Admin auth.
    """

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        self._captcha_success = None
        self._captcha_invalidated = False
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field, SliderCaptchaField):
                field._captcha_managed = True

    def _captcha_context(self):
        challenge_policy()
        fields = [(name, field) for name, field in self.fields.items() if isinstance(field, SliderCaptchaField)]
        allowed = purposes()
        if not fields or self.request is None or not session_binding(self.request):
            raise ValueError("Missing CAPTCHA request, binding or field")
        values = []
        for name, field in fields:
            raw = field.widget.value_from_datadict(self.data, self.files, self.add_prefix(name))
            if not isinstance(raw, str) or not field.required or field.disabled or field.purpose not in allowed:
                raise ValueError("Invalid CAPTCHA field context")
            values.append((name, field.purpose, raw, self.cleaned_data.get(name)))
        return self.request, session_binding(self.request), tuple(values)

    def _captcha_matches(self, context):
        return context[0] is self._captcha_success[0] and context[1:] == self._captcha_success[1:]

    @property
    def errors(self):
        # Django caches validation in _errors. Even when full_clean is skipped,
        # revisit a consumed proof's context; a detected change latches failure.
        errors = super().errors
        if (self._captcha_success is not None and not getattr(self, "_captcha_cleaning", False)
                and not getattr(self, "_captcha_check_errors", False)):
            try:
                unchanged = self._captcha_matches(self._captcha_context())
            except (ValueError, TypeError):
                unchanged = False
            self._captcha_invalidated |= not unchanged
            if self._captcha_invalidated and not errors.get("__all__"):
                self._captcha_check_errors = True
                try:
                    # add_error itself reads errors. This flag prevents reentry
                    # while recording this one context-change error.
                    self.add_error(None, ValidationError(CAPTCHA_ERROR, code="captcha_context_changed"))
                finally:
                    self._captcha_check_errors = False
        return errors

    def full_clean(self):
        # BaseForm/ModelForm consult errors while rebuilding cleaned_data. Do
        # not compare a half-built context with the successful snapshot; compare
        # once at _captcha_finish_clean, after all field/model validation.
        self._captcha_cleaning = True
        try:
            super().full_clean()
            self._captcha_finish_clean()
        finally:
            self._captcha_cleaning = False

    def _captcha_finish_clean(self):
        if not self.is_bound:
            return
        # Django ignores untouched extra formset forms. They protect no operation
        # and have no cleaned fields; preserve that behavior without consumption.
        if self.empty_permitted and not self.has_changed() and self._captcha_success is None:
            return
        try:
            context = self._captcha_context()
        except (ValueError, TypeError):
            self._captcha_invalidated |= self._captcha_success is not None
            self.add_error(None, ValidationError(CAPTCHA_ERROR, code="captcha_invalid"))
            return
        if self._captcha_success is not None:
            self._captcha_invalidated |= not self._captcha_matches(context)
            if self._captcha_invalidated:
                self.add_error(None, ValidationError(CAPTCHA_ERROR, code="captcha_context_changed"))
            return
        if self._errors:
            return
        if any(not isinstance(cleaned, str) for _name, _purpose, _raw, cleaned in context[2]):
            self.add_error(None, ValidationError(CAPTCHA_ERROR, code="captcha_invalid"))
            return
        try:
            with transaction.atomic(using=router.db_for_write(Challenge)):
                for _name, purpose, _raw, cleaned in context[2]:
                    if not consume(cleaned, self.request, purpose=purpose):
                        raise ValidationError(CAPTCHA_ERROR, code="captcha_invalid")
        except (ValidationError, DatabaseError):
            self.add_error(None, ValidationError(CAPTCHA_ERROR, code="captcha_invalid"))
            return
        self._captcha_success = context


class SliderAdminAuthenticationForm(AdminAuthenticationForm):
    nova_slider_token = forms.CharField(label=_("Security verification"), required=True, max_length=128, widget=SliderCaptchaWidget, error_messages={"required": _("Complete the security verification before signing in.")})

    def clean(self):
        # Validate/consume before authentication so missing/invalid CAPTCHA never
        # reaches password backends. A failed password requires a fresh proof.
        token = self.cleaned_data.get("nova_slider_token")
        if not token or self.request is None or not consume(token, self.request, purpose="login"):
            raise ValidationError(_("Security verification is missing, expired, or already used. Please try again."), code="captcha_invalid")
        return super().clean()
