"""Run after probe.py, against its disposable database only."""
import json
import os

assert os.environ.get('NOVA_TEST_DB'), 'Specify the isolated probe database'
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tests.settings')
import django
django.setup()
from django.contrib.sessions.models import Session
from django.test import Client, override_settings

with override_settings(CSRF_USE_SESSIONS=True):
    before = Session.objects.count()
    response = Client().get('/captcha/init', HTTP_ORIGIN='https://different.example', HTTP_SEC_FETCH_SITE='cross-site')
    print(json.dumps({'status': response.status_code, 'sessions_added': Session.objects.count() - before}))
