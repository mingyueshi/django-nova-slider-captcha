"""Loopback-only browser acceptance with real Django endpoints and private SQLite.

Run from the repository root with PYTHONPATH=src:., DJANGO_SETTINGS_MODULE=tests.settings,
and a private NOVA_TEST_DB path. The alternative landing page performs no operation.
"""
import os
from pathlib import Path
from wsgiref.simple_server import make_server

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
assert os.environ.get("NOVA_TEST_DB"), "Use a private database"
import django
from django.conf import settings
settings.ROOT_URLCONF = __name__
settings.NOVA_SLIDER_RATE_LIMITS = {key: 1000 for key in ("issue_session", "issue_ip", "verify_session", "verify_ip")}
django.setup()

from django.contrib.staticfiles.handlers import StaticFilesHandler
from django.core.management import call_command
from django.core.wsgi import get_wsgi_application
from django.http import HttpResponse
from django.urls import include, path
from nova_slider_captcha.forms import SliderCaptchaWidget


def widget_page(request):
    mode = request.GET.get("mode", "light")
    assert mode in ("auto", "light", "dark", "nova-light", "nova-dark")
    width = int(request.GET.get("width", "240"))
    assert 160 <= width <= 600
    scripted = request.GET.get("js", "1") == "1"
    theme = '' if mode.startswith("nova-") or mode == "auto" else f' data-theme="{mode}"'
    body_class = mode.replace("nova-", "nova-mode-") if mode.startswith("nova-") else ('independent-auto' if mode == "auto" else '')
    dark = mode.endswith("dark")
    label = "使用站点提供的安全非视觉验证与人工支持入口 — LongLabelWithoutBreaks012345678901234567890"
    widget = SliderCaptchaWidget(alternative_url="/audit/assistance/", alternative_label=label)
    markup = widget.render("first-proof", None, {"id": "proof-one"})
    markup += widget.render("second-proof", None, {"id": "proof-two"})
    django_css = ''
    if request.GET.get("host") == "django":
        directory = Path(django.__file__).parent / "contrib/admin/static/admin/css"
        django_css = (directory / "base.css").read_text() + (directory / "dark_mode.css").read_text()
    script = '<script defer src="/static/nova_slider_captcha/slider.js"></script>' if scripted else ''
    background, foreground = ("#111722", "#e7edf5") if dark else ("#ffffff", "#23283a")
    html = f'''<!doctype html><html lang="zh-Hans"{theme}><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>独立验收：宿主替代入口</title>
<style>{django_css}</style><link rel="stylesheet" href="/static/nova_slider_captcha/slider.css">{script}
<style>body{{margin:0;padding:12px;background:{background};color:{foreground};font-family:system-ui}}
main{{width:{width}px;max-width:100%;box-sizing:border-box}}.nova-slider-form-widget{{margin-bottom:24px}}
h1{{font-size:16px}}a:focus-visible{{outline:3px solid currentColor;outline-offset:3px}}
@media(prefers-color-scheme:dark){{body.independent-auto{{background:#111722;color:#e7edf5}}}}</style>
</head><body class="{body_class}"><main><h1>宿主替代入口独立验收</h1>{markup}</main></body></html>'''
    return HttpResponse(html)


def assistance(request):
    return HttpResponse("<!doctype html><html lang='zh-Hans'><title>宿主支持入口</title>"
                        "<h1>宿主支持入口</h1><p>仅用于导航验收；没有签发凭证或执行受保护操作。</p></html>")


urlpatterns = [
    path("captcha/", include("nova_slider_captcha.urls")),
    path("captcha-demo/", include("nova_slider_captcha.demo_urls")),
    path("audit/widget/", widget_page),
    path("audit/assistance/", assistance),
]

if __name__ == "__main__":
    call_command("migrate", verbosity=0, interactive=False)
    with make_server("127.0.0.1", 0, StaticFilesHandler(get_wsgi_application())) as server:
        print(f"http://127.0.0.1:{server.server_port}/audit/widget/", flush=True)
        server.serve_forever()
