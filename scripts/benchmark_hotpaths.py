"""Local image/SQL microbenchmark; uses only an isolated in-memory SQLite DB.

PYTHONPATH=src:. python scripts/benchmark_hotpaths.py --baseline-ref 33b92ec
The reference is read with git show; no checkout, migration or service is changed.
"""
import argparse
from collections import Counter
import json
import os
import platform
import statistics
import subprocess
import sys
from time import perf_counter
from types import ModuleType, SimpleNamespace

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "tests.settings")
from django.conf import settings
settings.DATABASES["default"]["NAME"] = ":memory:"
import django
django.setup()
import PIL
from django.db import connection
from django.test.utils import CaptureQueriesContext
from nova_slider_captcha import images, services
from nova_slider_captcha.models import RateLimitState


def baseline_module(ref, name):
    path = f"src/nova_slider_captcha/{name}.py"
    source = subprocess.check_output(["git", "show", f"{ref}:{path}"], text=True)
    module = ModuleType(f"nova_benchmark_baseline_{name}")
    module.__package__ = "nova_slider_captcha"
    sys.modules[module.__name__] = module
    exec(compile(source, f"{ref}:{path}", "exec"), module.__dict__)
    return module


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-ref", required=True)
    parser.add_argument("--iterations", type=int, default=15)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("iterations must be positive")
    old_images = baseline_module(args.baseline_ref, "images")
    old_services = baseline_module(args.baseline_ref, "services")
    timings = {"baseline": [], "current": []}
    generators = {"baseline": old_images.make_puzzle, "current": images.make_puzzle}
    for generate in generators.values():
        generate()
    # Interleave to reduce drift from measuring the implementations in batches.
    for _ in range(args.iterations):
        for label, generate in generators.items():
            started = perf_counter()
            generate()
            timings[label].append((perf_counter() - started) * 1000)
    with connection.schema_editor() as editor:
        editor.create_model(RateLimitState)
    sql = {}
    for label, implementation in (("baseline", old_services), ("current", services)):
        RateLimitState.objects.all().delete()
        request = SimpleNamespace(session={"_nova_slider_binding": "benchmark"}, META={"REMOTE_ADDR": "192.0.2.1"})
        sql[label] = {}
        for stage in ("new", "existing"):
            with CaptureQueriesContext(connection) as queries:
                allowed = bool(implementation.allow_request(request, "issue"))
            assert allowed
            sql[label][stage] = {"count": len(queries), "statements": dict(Counter(query["sql"].split()[0] for query in queries))}
    print(json.dumps({
        "platform": platform.platform(), "python": platform.python_version(),
        "django": django.get_version(), "pillow": PIL.__version__,
        "baseline": subprocess.check_output(["git", "rev-parse", args.baseline_ref], text=True).strip(),
        "image_ms": {label: {"samples": values, "median": statistics.median(values), "min": min(values), "max": max(values)} for label, values in timings.items()},
        "sqlite_sql": sql,
        "limitations": "Single-process local microbenchmark, not production load or database-backend certification",
    }, indent=2))


if __name__ == "__main__":
    main()
