"""Isolated review probes; no source edits and no production databases."""
import copy
import io
import json
import os
from pathlib import Path
from unittest.mock import patch

root = Path(os.environ['NOVA_REVIEW_DIR'])
os.environ['DJANGO_SETTINGS_MODULE'] = 'tests.settings'
os.environ['NOVA_TEST_DB'] = str(root / 'default.sqlite3')
from django.conf import settings
settings.DATABASES['captcha'] = copy.deepcopy(settings.DATABASES['default'])
settings.DATABASES['captcha']['NAME'] = str(root / 'captcha.sqlite3')
settings.DATABASES['captcha']['TEST']['NAME'] = str(root / 'captcha-test.sqlite3')
import django
django.setup()
from django import forms
from django.core.management import call_command
from django.db import IntegrityError
from django.test import Client, RequestFactory, override_settings
from django.utils import timezone
from django.contrib.sessions.models import Session
from nova_slider_captcha import services, views
from nova_slider_captcha.forms import SliderAdminAuthenticationForm, SliderCaptchaField, SliderCaptchaFormMixin
from nova_slider_captcha.models import Challenge, RateLimitState
from nova_slider_captcha.checks import captcha_settings_check

for database in ('default', 'captcha'):
    call_command('migrate', database=database, verbosity=0, stdout=io.StringIO())
results = {'django': django.get_version()}

def request():
    req = RequestFactory().get('/')
    req.session = {}
    return req

def proof(req, purpose='demo', alias='default'):
    payload = services.issue(req, purpose)
    row = Challenge.objects.using(alias).get(pk=payload['challengeId'])
    verified = services.verify(req, row.pk, row.target_x)
    assert verified['ok'], verified
    return verified['token'], row

admin_cases = []
for data in ({'password':'wrong'}, {'username':' ' ,'password':'wrong'}, {'username':'someone'}, {'username':'someone','password':'wrong'}):
    req = request()
    token,row = proof(req,'login')
    with patch('django.contrib.auth.forms.authenticate', return_value=None) as authenticate:
        form=SliderAdminAuthenticationForm(req,data={**data,'nova_slider_token':token})
        valid=form.is_valid()
    row.refresh_from_db()
    admin_cases.append({'submitted_fields': sorted(data),'username_blank':not data.get('username','').strip(),
                        'valid':valid,'consumed':row.token_consumed,'backend_calls':authenticate.call_count,
                        'error_fields':list(form.errors)})
assert all(item['consumed'] for item in admin_cases)
assert [item['backend_calls'] for item in admin_cases] == [0,0,0,1]
results['admin'] = admin_cases

client=Client(enforce_csrf_checks=True)
init=client.get('/captcha/init')
req=RequestFactory().get('/');req.session=client.session
token,row=proof(req,'login')
response=client.post('/admin/login/',{'password':'wrong','nova_slider_token':token},HTTP_X_CSRFTOKEN=init.json()['csrfToken'])
row.refresh_from_db()
assert response.status_code == 200 and row.token_consumed
results['admin_http_missing_username']={'status':response.status_code,'consumed':row.token_consumed}

class TogetherRouter:
    def db_for_read(self,model,**hints):
        return 'captcha' if model._meta.app_label == 'nova_slider_captcha' else None
    def db_for_write(self,model,**hints):
        return 'captcha' if model._meta.app_label == 'nova_slider_captcha' else None

class SplitRouter(TogetherRouter):
    def db_for_read(self,model,**hints):
        return 'default' if model._meta.app_label == 'nova_slider_captcha' else None

class TwoProofs(SliderCaptchaFormMixin, forms.Form):
    first=SliderCaptchaField()
    second=SliderCaptchaField()

with override_settings(DATABASE_ROUTERS=[TogetherRouter()]):
    req=request();token,row=proof(req,alias='captcha')
    assert services.consume(token,req,'demo')
    row.refresh_from_db(using='captcha')
    assert row.token_consumed
    rollback_token,rollback_row=proof(req,alias='captcha')
    invalid=TwoProofs(data={'first':rollback_token,'second':'X'*43},request=req)
    assert not invalid.is_valid()
    rollback_row.refresh_from_db(using='captcha')
    assert not rollback_row.token_consumed
    token_a,row_a=proof(req,alias='captcha');token_b,row_b=proof(req,alias='captcha')
    valid=TwoProofs(data={'first':token_a,'second':token_b},request=req)
    assert valid.is_valid(), valid.errors
    with override_settings(NOVA_SLIDER_RATE_LIMITS={'issue_ip':2,'issue_session':2}), patch('nova_slider_captcha.services.timezone.now',return_value=timezone.now()):
        decisions=[services.allow_request(req,'issue') for _ in range(3)]
    assert [d.allowed for d in decisions] == [True,True,False]
    assert decisions[-1].retry_after == 30
    assert RateLimitState.objects.using('default').count() == 0
    assert RateLimitState.objects.using('captcha').count() == 2
    results['together_router']={'issue_verify_consume':'passed','multi_proof_rollback':'passed','multi_proof_commit':'passed',
                                'quota_allowed':[d.allowed for d in decisions],'retry_after':decisions[-1].retry_after,
                                'default_quota_rows':0,'captcha_quota_rows':2}

with override_settings(DATABASE_ROUTERS=[SplitRouter()]):
    req=request();payload=services.issue(req,'demo')
    row=Challenge.objects.using('captcha').get(pk=payload['challengeId'])
    unavailable=services.verify(req,row.pk,row.target_x)
    assert unavailable['code']=='invalid_challenge'
    # Mimic a replica which received creation but not the subsequent UPDATE.
    values={field.attname:getattr(row,field.attname) for field in row._meta.concrete_fields}
    Challenge.objects.using('default').create(**values)
    wrong=services.verify(req,row.pk,row.target_x+20)
    primary_attempts=Challenge.objects.using('captcha').get(pk=row.pk).attempts
    assert primary_attempts==1 and wrong['attemptsRemaining']==5
    with override_settings(DATABASE_ROUTERS=[TogetherRouter()]):
        token,solved=proof(req,alias='captcha')
    consumed=services.consume(token,req,'demo')
    assert consumed
    results['split_router']={'fresh_challenge_code':unavailable['code'],'wrong_guess_reported_remaining':wrong['attemptsRemaining'],
                             'primary_attempts':primary_attempts,'consume_primary_token':consumed}

before=Session.objects.count()
statuses=[Client().get('/captcha/init').status_code for _ in range(45)]
created=Session.objects.count()-before
assert created==45 and set(statuses)=={200}
reuse=Client();reuse.get('/captcha/init');before_reuse=Session.objects.count()
for _ in range(3):reuse.get('/captcha/init')
assert Session.objects.count()==before_reuse
with override_settings(SESSION_ENGINE='django.contrib.sessions.backends.signed_cookies'):
    before_signed=Session.objects.count()
    signed=Client().get('/captcha/init')
    assert signed.status_code==200 and Session.objects.count()==before_signed
results['init']={'cookieless_requests':45,'responses':{'200':45},'database_sessions_created':created,
                 'session_cookie_age_seconds':settings.SESSION_COOKIE_AGE,'cookie_reuse_creates_extra_session':False,
                 'signed_cookie_backend_creates_database_session':False}

missing=RequestFactory().get('/')
try:
    services.issue(missing,'demo')
except IntegrityError:
    results['direct_issue_without_session']='IntegrityError'
else:
    raise AssertionError('Expected missing-session error')
with override_settings(MIDDLEWARE=['django.middleware.csrf.CsrfViewMiddleware']):
    no_session=Client(enforce_csrf_checks=True)
    initialized=no_session.get('/captcha/init')
    rejected=no_session.post('/captcha/challenge',data=json.dumps({'purpose':'demo'}),content_type='application/json',
                             HTTP_X_CSRFTOKEN=initialized.json()['csrfToken'])
    assert rejected.status_code==409 and rejected.json()['code']=='init_required'
    results['http_without_session_middleware']={'init_status':initialized.status_code,'challenge_status':rejected.status_code,
                                               'challenge_code':rejected.json()['code'],'checks':[e.id for e in captcha_settings_check(None)]}

for engine in ['django.contrib.sessions.backends.db','django.contrib.sessions.backends.signed_cookies']:
    with override_settings(INSTALLED_APPS=[app for app in settings.INSTALLED_APPS if app != 'django.contrib.sessions'],SESSION_ENGINE=engine):
        results.setdefault('own_checks_without_sessions_app',{})[engine]=[e.id for e in captcha_settings_check(None)]

exact=RequestFactory().get('/',secure=True,HTTP_HOST='testserver',HTTP_ORIGIN='https://testserver')
port=RequestFactory().get('/',secure=True,HTTP_HOST='testserver:443',HTTP_ORIGIN='https://testserver')
results['default_port_origin']={'canonical_host':views.same_origin(exact),'explicit_default_port_host':views.same_origin(port)}
assert results['default_port_origin']=={'canonical_host':True,'explicit_default_port_host':False}

# Verify these are snapshot literals, not F('field') self-comparisons.
row=Challenge.objects.using('default').first()
old_tolerance=row.tolerance
Challenge.objects.using('default').filter(pk=row.pk).update(tolerance=old_tolerance+1)
guard=Challenge.objects.using('default').filter(pk=row.pk,max_attempts=row.max_attempts,tolerance=row.tolerance)
assert not guard.exists()
results['policy_snapshot_guard']={'matches_after_concurrent_policy_change':False}
(root/'results.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
