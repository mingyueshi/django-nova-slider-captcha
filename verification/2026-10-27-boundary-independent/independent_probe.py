"""Main-chat acceptance probes using isolated DBs and real middleware/service paths."""
import copy
from concurrent.futures import ThreadPoolExecutor
import io
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

root = Path(os.environ['NOVA_REVIEW_DIR'])
os.environ['DJANGO_SETTINGS_MODULE'] = 'tests.settings'
os.environ['NOVA_TEST_DB'] = str(root / 'probe-default.sqlite3')
from django.conf import settings
settings.DATABASES['captcha'] = copy.deepcopy(settings.DATABASES['default'])
settings.DATABASES['captcha']['NAME'] = str(root / 'probe-primary.sqlite3')
settings.DATABASES['captcha']['TEST']['NAME'] = str(root / 'probe-primary-test.sqlite3')
import django
django.setup()
from django import forms
from django.contrib.sessions.models import Session
from django.core.management import call_command
from django.db import DatabaseError, close_old_connections
from django.db.models.query import QuerySet
from django.test import Client, RequestFactory, override_settings
from django.utils import timezone
from nova_slider_captcha import services
from nova_slider_captcha.forms import SliderAdminAuthenticationForm, SliderCaptchaField, SliderCaptchaFormMixin
from nova_slider_captcha.models import Challenge, RateLimitState

for alias in ('default', 'captcha'):
    call_command('migrate', database=alias, verbosity=0, stdout=io.StringIO())
results = {'runtime': {'django': django.get_version()}, 'checks': []}

def record(name, detail):
    results['checks'].append({'name': name, **detail})

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

class ExtraAdmin(SliderAdminAuthenticationForm):
    host_required = forms.CharField()

for name, cls, data in (
    ('missing_username', SliderAdminAuthenticationForm, {'password': 'wrong'}),
    ('blank_username', SliderAdminAuthenticationForm, {'username': '  ', 'password': 'wrong'}),
    ('missing_password', SliderAdminAuthenticationForm, {'username': 'someone'}),
    ('missing_both', SliderAdminAuthenticationForm, {}),
    ('host_field_invalid', ExtraAdmin, {'username': 'someone', 'password': 'wrong'}),
):
    req = request()
    token, row = proof(req, 'login')
    with patch('django.contrib.auth.forms.authenticate') as authenticate:
        form = cls(req, data={**data, 'nova_slider_token': token})
        assert not form.is_valid()
        assert not form.is_valid()
        assert authenticate.call_count == 0
    row.refresh_from_db()
    assert not row.token_consumed
    record(name, {'consumed': False, 'authenticate_calls': 0, 'errors': list(form.errors)})

for token_kind in ('missing', 'malformed', 'unknown', 'other_purpose', 'expired'):
    req = request()
    token, row = proof(req, 'demo' if token_kind == 'other_purpose' else 'login')
    if token_kind == 'expired':
        Challenge.objects.filter(pk=row.pk).update(token_expires_at=timezone.now())
    submitted = {'missing': '', 'malformed': 'short', 'unknown': 'X' * 43}.get(token_kind, token)
    with patch('django.contrib.auth.forms.authenticate') as authenticate:
        form = SliderAdminAuthenticationForm(req, data={'username': 'someone', 'password': 'wrong', 'nova_slider_token': submitted})
        assert not form.is_valid()
        assert not authenticate.called
    row.refresh_from_db()
    assert not row.token_consumed
    record('admin_proof_' + token_kind, {'authenticate_calls': 0, 'consumed': False})

for name, user in (('bad_password', None), ('valid_login', SimpleNamespace(is_active=True, is_staff=True))):
    req = request()
    token, row = proof(req, 'login')
    def auth_after_consume(*args, **kwargs):
        assert Challenge.objects.get(pk=row.pk).token_consumed
        return user
    with patch('django.contrib.auth.forms.authenticate', side_effect=auth_after_consume) as authenticate:
        form = SliderAdminAuthenticationForm(req, data={'username': 'someone', 'password': 'password', 'nova_slider_token': token})
        assert form.is_valid() == (user is not None)
        assert form.is_valid() == (user is not None)
        assert authenticate.call_count == 1
    row.refresh_from_db()
    assert row.token_consumed
    with patch('django.contrib.auth.forms.authenticate') as authenticate:
        repeated = SliderAdminAuthenticationForm(req, data={'username': 'someone', 'password': 'password', 'nova_slider_token': token})
        assert not repeated.is_valid()
        assert not authenticate.called
    record('admin_' + name, {'consume_before_auth': True, 'authenticate_calls': 1, 'replay_rejected': True})

client = Client(enforce_csrf_checks=True)
initialized = client.get('/captcha/init')
req = RequestFactory().get('/')
req.session = client.session
token, row = proof(req, 'login')
response = client.post('/admin/login/', {'password': 'wrong', 'nova_slider_token': token}, HTTP_X_CSRFTOKEN=initialized.json()['csrfToken'])
row.refresh_from_db()
assert response.status_code == 200 and not row.token_consumed
assert token.encode() not in response.content
record('admin_real_csrf_post_missing_username', {'status': 200, 'consumed': False, 'token_echoed': False})

class SplitRouter:
    def db_for_read(self, model, **hints):
        return 'default' if model._meta.app_label == 'nova_slider_captcha' else None
    def db_for_write(self, model, **hints):
        return 'captcha' if model._meta.app_label == 'nova_slider_captcha' else None

class TwoProofs(SliderCaptchaFormMixin, forms.Form):
    first = SliderCaptchaField()
    second = SliderCaptchaField()

with override_settings(DATABASE_ROUTERS=[SplitRouter()]):
    req = request()
    token, fresh = proof(req, alias='captcha')
    assert not Challenge.objects.using('default').filter(pk=fresh.pk).exists()
    assert services.consume(token, req, 'demo')
    assert not services.consume(token, req, 'demo')
    record('primary_only_challenge', {'verify': True, 'consume': True, 'replay': False})
    payload = services.issue(req, 'demo')
    row = Challenge.objects.using('captcha').get(pk=payload['challengeId'])
    Challenge.objects.using('default').create(**{field.attname: getattr(row, field.attname) for field in row._meta.concrete_fields})
    for remaining in (4, 3):
        wrong = services.verify(req, row.pk, row.target_x + 20)
        assert wrong['code'] == 'incorrect' and wrong['attemptsRemaining'] == remaining, wrong
    assert Challenge.objects.using('default').get(pk=row.pk).attempts == 0
    solved = services.verify(req, row.pk, row.target_x)
    assert solved['ok']
    assert services.verify(req, row.pk, row.target_x)['code'] == 'already_verified'
    record('lagging_replica', {'remaining': [4, 3], 'replica_attempts': 0, 'primary_solved_respected': True})
    first, row = proof(req, alias='captcha')
    rejected = TwoProofs(data={'first': first, 'second': 'X' * 43}, request=req)
    assert not rejected.is_valid()
    row.refresh_from_db(using='captcha')
    assert not row.token_consumed
    second, other = proof(req, alias='captcha')
    accepted = TwoProofs(data={'first': first, 'second': second}, request=req)
    assert accepted.is_valid(), accepted.errors
    assert all(Challenge.objects.using('captcha').get(pk=pk).token_consumed for pk in (row.pk, other.pk))
    record('primary_multi_proof_atomicity', {'rollback': True, 'commit': True})
    with override_settings(NOVA_SLIDER_RATE_LIMITS={'issue_ip': 2, 'issue_session': 2}), patch('nova_slider_captcha.services.timezone.now', return_value=timezone.now()):
        decisions = [services.allow_request(req, 'issue') for _ in range(3)]
    assert [decision.allowed for decision in decisions] == [True, True, False]
    assert decisions[-1].retry_after == 30
    record('primary_gcra_retry', {'allowed': [True, True, False], 'retry_after': 30})

for csrf_session in (False, True):
    RateLimitState.objects.all().delete()
    with override_settings(CSRF_USE_SESSIONS=csrf_session, NOVA_SLIDER_RATE_LIMITS={'init_ip': 2}), patch('nova_slider_captcha.services.timezone.now', return_value=timezone.now()):
        before = Session.objects.count()
        first = Client(enforce_csrf_checks=True)
        second = Client(enforce_csrf_checks=True)
        initialized = first.get('/captcha/init')
        assert initialized.status_code == second.get('/captcha/init').status_code == 200
        assert Session.objects.count() - before == 2
        state = list(RateLimitState.objects.values('key', 'tat_us', 'blocked_until_us'))
        for _ in range(3):
            denied = Client(enforce_csrf_checks=True).get('/captcha/init', HTTP_X_FORWARDED_FOR='192.0.2.200')
            assert denied.status_code == 429, denied.content
            assert denied.json()['retryAfter'] == int(denied['Retry-After']) == 30
            assert settings.SESSION_COOKIE_NAME not in denied.cookies
        assert Session.objects.count() - before == 2
        assert list(RateLimitState.objects.values('key', 'tat_us', 'blocked_until_us')) == state
        reused = first.get('/captcha/init')
        assert reused.status_code == 200
        assert Session.objects.count() - before == 2
        # Use the real middleware-issued CSRF token for a successful API POST.
        challenge = first.post('/captcha/challenge', json.dumps({'purpose': 'demo'}), content_type='application/json', HTTP_X_CSRFTOKEN=reused.json()['csrfToken'])
        assert challenge.status_code == 200, challenge.content
        origin = Client().get('/captcha/init', HTTP_ORIGIN='https://untrusted.invalid')
        assert origin.status_code == 403
        assert Session.objects.count() - before == 2
        new_peer = Client().get('/captcha/init', REMOTE_ADDR='192.0.2.8')
        assert new_peer.status_code == 200
        record('init_real_middleware_' + str(csrf_session), {'accepted_new_sessions': 2, 'denied': 3, 'denial_sessions': 0, 'retry_after': 30, 'debt_unchanged': True, 'bound_reuse': True, 'csrf_post_status': 200, 'cross_origin_sessions': 0, 'other_peer_status': 200})

# Fresh HTTP clients race on the same direct-peer quota; denied clients must
# never materialize DB sessions, including when CSRF is session-backed.
RateLimitState.objects.all().delete()
with override_settings(CSRF_USE_SESSIONS=True, NOVA_SLIDER_RATE_LIMITS={'init_ip': 3}), patch('nova_slider_captcha.services.timezone.now', return_value=timezone.now()):
    before = Session.objects.count()
    def initialize_peer(_):
        close_old_connections()
        try:
            response = Client().get('/captcha/init')
            return response.status_code
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=8) as pool:
        statuses = list(pool.map(initialize_peer, range(8)))
    assert statuses.count(200) == 3, statuses
    assert all(status in (200, 429) for status in statuses), statuses
    assert Session.objects.count() - before == 3
    record('concurrent_init', {'requests': 8, 'accepted': 3, 'limited': 5, 'sessions_added': 3})

for csrf_session in (False, True):
    with override_settings(CSRF_USE_SESSIONS=csrf_session, NOVA_SLIDER_RATE_LIMITS={'init_ip': True}):
        before = Session.objects.count()
        response = Client().get('/captcha/init')
        assert response.status_code == 503 and response.json()['code'] == 'configuration_invalid'
        assert Session.objects.count() == before
    with override_settings(CSRF_USE_SESSIONS=csrf_session), patch.object(QuerySet, 'update', side_effect=DatabaseError('probe only')):
        before = Session.objects.count()
        response = Client().get('/captcha/init')
        assert response.status_code == 503 and response.json()['code'] == 'rate_limit_unavailable'
        assert Session.objects.count() == before
    record('init_failure_' + str(csrf_session), {'invalid_bool': 503, 'database_failure': 503, 'new_sessions': 0})

RateLimitState.objects.all().delete()
for csrf_session in (False, True):
    with override_settings(CSRF_USE_SESSIONS=csrf_session):
        client = Client()
        session = client.session
        session['_nova_slider_binding'] = 123
        session.save()
        before = Session.objects.count()
        response = client.get('/captcha/init')
        assert response.status_code == 503 and response.json()['code'] == 'configuration_invalid', response.content
        assert Session.objects.count() == before
        record('invalid_binding_' + str(csrf_session), {'status': 503, 'new_sessions': 0})

with override_settings(MIDDLEWARE=['django.middleware.csrf.CsrfViewMiddleware']):
    response = Client().get('/captcha/init')
    assert response.status_code == 503 and response.json()['code'] == 'configuration_invalid'
record('missing_session_middleware_init', {'status': 503})
with patch('nova_slider_captcha.services.make_puzzle') as image:
    try:
        services.issue(RequestFactory().get('/'), 'demo')
    except ValueError:
        pass
    else:
        raise AssertionError('Direct issue must reject missing session')
    assert not image.called
record('direct_issue_precondition', {'error': 'ValueError', 'image_called': False})

(root / 'probe-results.json').write_text(json.dumps(results, indent=2) + '\n')
print(json.dumps(results, indent=2))
