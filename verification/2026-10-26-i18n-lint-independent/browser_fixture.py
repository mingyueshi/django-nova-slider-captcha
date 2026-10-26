"""Temporary loopback-only Django fixture for browser locale review."""
import json
import os
from pathlib import Path
from wsgiref.simple_server import make_server

assert os.environ.get("NOVA_TEST_DB")
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
import django
django.setup()
from django.conf import settings
from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application
from django.http import HttpResponse, QueryDict
from django.utils.translation import override
from nova_slider_captcha.forms import SliderCaptchaWidget

call_command("migrate", verbosity=0)
settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost"]
django_app = StaticFilesHandler(get_wsgi_application())

def application(environ, start_response):
    if environ["PATH_INFO"] != "/locale-review/":
        return django_app(environ, start_response)
    language = QueryDict(environ.get("QUERY_STRING", "")).get("lang", "fr")
    if language not in ("fr", "ja", "en", "zh-hans"):
        language = "fr"
    with override(language):
        widget = SliderCaptchaWidget(purpose="demo")
        rendered = widget.render("nova_slider_token", None)
    html = f'''<!doctype html><html lang="{language}"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1"><title>Local locale review</title>
    {widget.media}<style>body{{font:16px system-ui;margin:32px;max-width:600px}}button{{margin:4px;padding:8px}}</style></head>
    <body><h1>Local language fallback review</h1><p>Django language: {language}</p>
    <form>{rendered}</form><nav aria-label="Review language controls">
    <button type="button" onclick="document.querySelector('nova-slider').setLocale('fr-FR')">Français</button>
    <button type="button" onclick="document.querySelector('nova-slider').locale='ja-JP'">日本語</button>
    <button type="button" onclick="document.querySelector('nova-slider').setAttribute('locale','zh-Hans')">简体中文</button>
    <button type="button" onclick="document.querySelector('nova-slider').removeAttribute('locale')">Default</button>
    </nav></body></html>'''
    response = HttpResponse(html)
    start_response("200 OK", list(response.items()))
    return [response.content]

with make_server("127.0.0.1", 0, application) as server:
    receipt = {"url":f"http://127.0.0.1:{server.server_port}/locale-review/?lang=fr",
               "scope":"Isolated local Django render and language controls; no login or CAPTCHA solving"}
    Path(os.environ["NOVA_BROWSER_RECEIPT"]).write_text(json.dumps(receipt)+"\n")
    print(json.dumps(receipt), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
