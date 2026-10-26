"""Independent concurrent rendering and bounded warning acceptance."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
import django
django.setup()
from django.test import override_settings
from nova_slider_captcha import events
from nova_slider_captcha.forms import SliderCaptchaWidget

records = []


def capture(level, message, **kwargs):
    records.append({"level": level, "message": message, **kwargs})


def render(_=None):
    html = SliderCaptchaWidget().render("proof", None)
    assert "<nova-slider" in html
    assert 'class="nsc-alternative"' not in html
    return True


with override_settings(NOVA_SLIDER_ALTERNATIVE_URL="https://invalid.example/url-private-marker",
                       NOVA_SLIDER_ALTERNATIVE_LABEL="label-private-marker"):
    with patch.object(events, "monotonic", return_value=10_000_000):
        with patch.object(events.logger, "log", side_effect=capture):
            with ThreadPoolExecutor(max_workers=8) as pool:
                assert all(pool.map(render, range(32)))
    assert len(records) == 1
    assert records[0]["extra"]["captcha_event"] == "optional_link"
    assert records[0]["extra"]["captcha_reason"] == "configuration_invalid"
    assert records[0]["level"] == 30
    encoded = json.dumps(records)
    assert "url-private-marker" not in encoded and "label-private-marker" not in encoded
    assert "exc_info" not in records[0]

    with patch.object(events, "monotonic", return_value=10_000_299):
        with patch.object(events.logger, "log", side_effect=capture):
            render()
    assert len(records) == 1

    # A failing sink claims the next slot but must not affect rendering or retry
    # on every render. This actually executes the patched failing logger once.
    with patch.object(events, "monotonic", return_value=10_000_300):
        with patch.object(events.logger, "log", side_effect=RuntimeError("synthetic broken sink")) as broken:
            render()
            render()
            assert broken.call_count == 1

    with override_settings(NOVA_SLIDER_ALTERNATIVE_URL="/fixed/", NOVA_SLIDER_ALTERNATIVE_LABEL="Recovered"):
        assert 'href="/fixed/"' in SliderCaptchaWidget().render("proof", None)

    with patch.object(events, "monotonic", return_value=10_000_600):
        with patch.object(events.logger, "log", side_effect=capture):
            render()
    assert len(records) == 2

result = {"concurrent_renders": 32, "warnings_first_window": 1,
          "suppressed_before_300_seconds": True, "broken_sink_executed_once": True,
          "configuration_recovery_immediate": True, "next_window_warns": True,
          "no_configuration_values_or_exception_text_logged": True,
          "limitations": "Synthetic clock; process-local bound, not cross-worker aggregation"}
Path(sys.argv[1]).write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result))
