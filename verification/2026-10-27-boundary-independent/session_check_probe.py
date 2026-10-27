"""Fresh-process system checks: no inherited Django app/model registry."""
import json
import sys
from tempfile import TemporaryDirectory
from django.conf import settings

engine, installed = sys.argv[1:]
tmp = TemporaryDirectory(prefix="nova-independent-session-")
apps = ['nova_slider_captcha']
if installed == 'yes':
    apps += ['django.contrib.sessions.apps.SessionsConfig']
settings.configure(
    SECRET_KEY='isolated-review-key-not-a-deployment-secret',
    INSTALLED_APPS=apps,
    MIDDLEWARE=['django.contrib.sessions.middleware.SessionMiddleware', 'django.middleware.csrf.CsrfViewMiddleware'],
    DATABASES={'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': ':memory:'}},
    SESSION_ENGINE=engine,
    ROOT_URLCONF="nova_slider_captcha.urls",
    ALLOWED_HOSTS=["testserver"],
    SESSION_FILE_PATH=tmp.name,
)
import django
django.setup()
from nova_slider_captcha.checks import captcha_settings_check
errors = [{'id': error.id, 'message': str(error.msg)} for error in captcha_settings_check(None)]
expected = installed == 'no' and engine in ('django.contrib.sessions.backends.db', 'django.contrib.sessions.backends.cached_db')
assert bool(errors) == expected, errors
from django.core.management import call_command
from django.test import Client
call_command('migrate', verbosity=0)
client = Client(enforce_csrf_checks=True)
response = client.get('/init')
assert response.status_code == (503 if expected else 200), response.content
if expected:
    assert response.json()['code'] == 'configuration_invalid'
    assert not response.cookies
    challenge_status = None
else:
    challenge = client.post('/challenge', json.dumps({'purpose': 'demo'}), content_type='application/json', HTTP_X_CSRFTOKEN=response.json()['csrfToken'])
    assert challenge.status_code == 200, challenge.content
    challenge_status = challenge.status_code
print(json.dumps({'engine': engine, 'sessions_app': installed, 'errors': errors, 'init_status': response.status_code, 'challenge_status': challenge_status, 'passed': True}))
tmp.cleanup()
