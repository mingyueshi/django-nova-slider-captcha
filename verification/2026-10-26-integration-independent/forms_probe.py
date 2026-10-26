"""Independent generic-form consumer behavior checks."""
import io,json
from types import SimpleNamespace
from django.conf import settings
settings.DATABASES['default']['NAME']=':memory:'
import django
django.setup()
from django import forms
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.forms import formset_factory
from django.test import override_settings
from nova_slider_captcha.forms import SliderCaptchaField,SliderCaptchaFormMixin
from nova_slider_captcha import services
from nova_slider_captcha.models import Challenge
call_command('migrate',verbosity=0)
request=SimpleNamespace(session={})
checks=[]
def mint(purpose='signup'):
    data=services.issue(request,purpose)
    row=Challenge.objects.get(pk=data['challengeId'])
    return services.verify(request,row.pk,row.target_x)['token'],row
class SignupForm(SliderCaptchaFormMixin,forms.Form):
    email=forms.EmailField()
    security=SliderCaptchaField(purpose='signup')
class SignupModelForm(SliderCaptchaFormMixin,forms.ModelForm):
    security=SliderCaptchaField(purpose='signup')
    class Meta:
        model=get_user_model()
        fields=['username']
with override_settings(NOVA_SLIDER_PURPOSES=['demo','login','signup','reset']):
    token,row=mint()
    form=SignupForm(data={'join-email':'invalid','join-security':token},prefix='join',request=request)
    assert not form.is_valid(); row.refresh_from_db(); assert not row.token_consumed
    form=SignupForm(data={'join-email':'u@example.com','join-security':token},prefix='join',request=request)
    assert form.is_valid(),form.errors
    for _ in range(3):
        form.full_clean(); assert form.is_valid(),form.errors
    row.refresh_from_db(); assert row.token_consumed
    assert not SignupForm(data={'email':'u@example.com','security':token},request=request).is_valid()
    checks.append('field errors retain proof, prefixed valid form consumes once, repeated validation stable, replay denied')
    fresh,freshrow=mint()
    form.data={'join-email':'u@example.com','join-security':fresh}
    assert not form.is_valid(); form.full_clean(); assert not form.is_valid()
    freshrow.refresh_from_db(); assert not freshrow.token_consumed
    checks.append('changed token cannot use cached success or consume replacement')
    get_user_model().objects.create(username='existing')
    token,row=mint()
    invalid=SignupModelForm(data={'username':'existing','security':token},request=request)
    assert not invalid.is_valid(); row.refresh_from_db(); assert not row.token_consumed
    valid=SignupModelForm(data={'username':'new-person','security':token},request=request)
    assert valid.is_valid(),valid.errors
    valid.save(); row.refresh_from_db(); assert row.token_consumed
    checks.append('ModelForm uniqueness failure retains proof; valid model form consumes and saves')
    token,row=mint()
    missing=SignupForm(data={'email':'u@example.com','security':token})
    assert not missing.is_valid(); row.refresh_from_db(); assert not row.token_consumed
    checks.append('missing request fails without consuming')
    class Transform(SignupForm):
        replacement=None
        def clean_security(self):
            return self.replacement or self.cleaned_data['security']
    original,originalrow=mint()
    replacement,replacementrow=mint()
    transformed=Transform({'email':'u@example.com','security':original},request=request)
    assert transformed.is_valid()
    transformed.replacement=replacement
    transformed.full_clean(); assert not transformed.is_valid()
    replacementrow.refresh_from_db(); assert not replacementrow.token_consumed
    transformed.replacement=None
    transformed.full_clean(); assert not transformed.is_valid()
    checks.append('changed cleaned token invalidates permanently and leaves replacement unconsumed')
    identity,identityrow=mint()
    identity_form=SignupForm({'email':'u@example.com','security':identity},request=request)
    assert identity_form.is_valid()
    identity_form.request=SimpleNamespace(session=request.session.copy())
    assert not identity_form.is_valid()
    identity_form.request=request
    identity_form.full_clean(); assert not identity_form.is_valid()
    checks.append('equal-valued replacement request cannot reuse cached identity')
    Set=formset_factory(SignupForm,extra=1)
    data={'form-TOTAL_FORMS':'2','form-INITIAL_FORMS':'0','form-MIN_NUM_FORMS':'0','form-MAX_NUM_FORMS':'1000','form-0-email':'u@example.com','form-0-security':token}
    formset=Set(data,form_kwargs={'request':request})
    assert formset.is_valid(),formset.errors
    checks.append('formset accepts one protected form plus empty extra form')
print(json.dumps({'status':'passed','checks':checks},indent=2))
