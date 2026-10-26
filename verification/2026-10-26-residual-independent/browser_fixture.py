"""Loopback-only fixture for optional-link failure; never a product endpoint."""
import json
import os
from pathlib import Path
from wsgiref.simple_server import make_server

assert os.environ.get("NOVA_TEST_DB"), "Use an isolated database"
assert os.environ.get("NOVA_BROWSER_RECEIPT"), "Choose a temporary receipt file"
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")

import django
django.setup()
from django.conf import settings
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application

# Initialize the disposable DB before installing intentionally invalid settings.
call_command("migrate", verbosity=0)
settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
settings.NOVA_SLIDER_ALTERNATIVE_URL = "javascript:invalid-host-configuration"
settings.NOVA_SLIDER_ALTERNATIVE_LABEL = "Invalid host link must not render"
application = StaticFilesHandler(get_wsgi_application())
with make_server("127.0.0.1", 0, application) as server:
    receipt = {"url": f"http://127.0.0.1:{server.server_port}/admin/login/",
               "scope": "Local invalid-global-link Admin render; no login or CAPTCHA solving"}
    Path(os.environ["NOVA_BROWSER_RECEIPT"]).write_text(json.dumps(receipt) + "\n")
    print(json.dumps(receipt), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
