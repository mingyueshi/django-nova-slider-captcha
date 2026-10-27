"""Fresh process: a sessions app is required only by database session engines."""
import json
import logging
import os
import sys
from pathlib import Path
from django.conf import settings

engine=sys.argv[1]
settings.configure(
    SECRET_KEY='isolated-review-only', DEBUG=False, ALLOWED_HOSTS=['testserver'],
    INSTALLED_APPS=['nova_slider_captcha'], ROOT_URLCONF='nova_slider_captcha.urls',
    MIDDLEWARE=['django.contrib.sessions.middleware.SessionMiddleware','django.middleware.csrf.CsrfViewMiddleware'],
    DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':str(Path(os.environ['NOVA_REVIEW_DIR'])/'fresh.sqlite3')}},
    SESSION_ENGINE=engine, USE_TZ=True,
)
logging.disable(logging.CRITICAL)
import django
django.setup()
from django.test import Client
from nova_slider_captcha.checks import captcha_settings_check
response=Client(raise_request_exception=False).get('/init')
print(json.dumps({'engine':engine,'checks':[e.id for e in captcha_settings_check(None)],
                  'status':response.status_code,'error_type':response.exc_info[0].__name__ if response.exc_info else None}))
