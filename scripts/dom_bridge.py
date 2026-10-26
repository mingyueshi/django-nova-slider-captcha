"""Test-only stdin bridge for DOM tests; never deployed as a web endpoint."""
import json
import io
import tempfile
import os
import sys
from pathlib import Path
from contextlib import nullcontext
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
os.environ["DJANGO_SETTINGS_MODULE"] = "tests.settings"
from django.conf import settings
temporary = tempfile.TemporaryDirectory(prefix="nova-slider-dom-")
settings.DATABASES["default"]["NAME"] = str(Path(temporary.name) / "test.sqlite3")
import django
django.setup()
from django.test import Client
from django.core.management import call_command
from django.utils.translation import override
call_command("migrate", verbosity=0, stdout=io.StringIO())
from nova_slider_captcha.models import Challenge
from django import forms
from nova_slider_captcha.forms import SliderCaptchaField, SliderCaptchaFormMixin


class AriaForm(SliderCaptchaFormMixin, forms.Form):
    proof = SliderCaptchaField()
    second = SliderCaptchaField()

client = Client(enforce_csrf_checks=True)
for line in sys.stdin:
    data = json.loads(line)
    try:
        if data.get("op") == "solution":
            result = {"x": Challenge.objects.get(pk=data["id"]).target_x}
        elif data.get("op") == "aria_form":
            form = AriaForm(data={} if data.get("bound") else None, prefix="account")
            for field in form.fields.values():
                field.help_text = "Use the secure alternative if needed." if data.get("help") else ""
            with override("en"):
                result = {"status": 200, "text": "<form>" + str(form.as_p()) + "</form>"}
        else:
            method = data.get("method", "GET")
            headers = {"HTTP_" + key.upper().replace("-", "_"): value for key, value in data.get("headers", {}).items() if key.lower() != "content-type"}
            with override(data["language"]) if data.get("language") else nullcontext():
                if method == "GET":
                    response = client.get(data["path"], **headers)
                else:
                    response = client.post(data["path"], data.get("body", ""), content_type="application/json", **headers)
            result = {"status": response.status_code, "text": response.content.decode()}
        print(json.dumps({"id": data["requestId"], "result": result}), flush=True)
    except Exception as error:
        print(json.dumps({"id": data["requestId"], "error": repr(error)}), flush=True)

temporary.cleanup()
