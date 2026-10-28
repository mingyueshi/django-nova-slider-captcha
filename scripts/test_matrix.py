"""Run source/wheel against the CI pairs, optionally also with Nova installed.

Usage: python scripts/test_matrix.py --runtimes /path/to/uv-install-dir --wheel /path/to/built.whl --work /path/to/new-results [--nova-source /path/to/nova/django-theme/src]
All environment creation and reports stay in the selected --work directory.
"""
import argparse
import hashlib
from concurrent.futures import ThreadPoolExecutor
import json
import os
import re
from pathlib import Path
import subprocess
import sys

CELLS = [
    ("3.10", "5.2.17", "12.2.0"),
    ("3.11", "5.2.17", "12.3.0"),
    ("3.12", "5.2.17", "12.3.0"),
    ("3.12", "6.1.2", "12.2.0"),
    ("3.13", "6.1.2", "12.3.0"),
    ("3.14", "6.0.9", "12.3.0"),
]
ROOT = Path(__file__).resolve().parent.parent


def find_interpreter(runtimes, version):
    """Accept uv's platform-specific layout and pyenv's version directories."""
    candidates = {*runtimes.glob(f"cpython-{version}*-*/bin/python3"), *runtimes.glob(f"{version}*/bin/python3")}
    matches = []
    for candidate in candidates:
        actual = subprocess.check_output([str(candidate), "-c", "import platform; print(platform.python_version())"], text=True).strip()
        if actual.startswith(version + "."):
            matches.append((tuple(map(int, actual.split("."))), candidate))
    if not matches:
        raise RuntimeError(f"No Python {version} runtime found in {runtimes}")
    return max(matches, key=lambda match: match[0])[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtimes", type=Path, required=True)
    parser.add_argument("--nova-source", type=Path)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--work", type=Path, default=Path("/tmp/nova-slider-matrix"))
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    args.runtimes = args.runtimes.resolve()
    args.wheel = args.wheel.resolve()
    args.work = args.work.resolve()
    args.work.mkdir(parents=True, exist_ok=True)

    def cell(spec):
        pyver, djver, pillow = spec
        directory = args.work / f"{pyver}-{djver}-{pillow}"
        directory.mkdir(exist_ok=True)
        log_path = directory / "run.log"
        result = {"python_series": pyver, "django": djver, "pillow": pillow, "profiles": [], "log": str(log_path)}
        with log_path.open("w") as log:
            def run(command, env=None):
                log.write("$ " + " ".join(map(str, command)) + "\n")
                log.flush()
                subprocess.run(list(map(str, command)), cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
            try:
                interpreter = find_interpreter(args.runtimes, pyver)
                run([interpreter, "-m", "venv", directory / "venv"])
                py = directory / "venv/bin/python"
                run([py, "-m", "pip", "install", "--disable-pip-version-check", f"Django=={djver}", f"Pillow=={pillow}", "asgiref==3.12.1", "sqlparse==0.6.0"])
                # Same-version rebuilds must not silently keep an older wheel.
                run([py, "-m", "pip", "install", "--disable-pip-version-check", "--force-reinstall", "--no-deps", args.wheel])
                run([py, "-m", "pip", "check"])
                result["python"] = subprocess.check_output([str(py), "-c", "import platform; print(platform.python_version())"], text=True).strip()
                run([py, "-c", f"import platform, django, PIL; assert platform.python_version().startswith({pyver!r} + '.'); assert django.get_version() == {djver!r}; assert PIL.__version__ == {pillow!r}; print(platform.python_version(), django.get_version(), PIL.__version__)"])
                for mode in ("source", "wheel"):
                    for theme in (("native", "nova") if args.nova_source else ("native",)):
                        profile = {"mode": mode, "theme": theme, "status": "running"}
                        result["profiles"].append(profile)
                        env = os.environ.copy()
                        paths = [str(ROOT)]
                        if mode == "source":
                            paths.insert(0, str(ROOT / "src"))
                        if theme == "nova":
                            paths.append(str(args.nova_source))
                        env.update(PYTHONPATH=os.pathsep.join(paths), PYTHONDONTWRITEBYTECODE="1", DJANGO_SETTINGS_MODULE="tests.nova_settings" if theme == "nova" else "tests.settings", NOVA_TEST_DB=str(directory / f"{mode}-{theme}.sqlite3"))
                        expected = str(ROOT / "src") if mode == "source" else str(directory / "venv")
                        run([py, "-c", f"import nova_slider_captcha; from pathlib import Path; p=Path(nova_slider_captcha.__file__).resolve(); print(p); assert str(p).startswith({expected!r})"], env)
                        run([py, "-m", "django", "check"], env)
                        run([py, "-m", "django", "makemigrations", "nova_slider_captcha", "--check", "--dry-run"], env)
                        run([py, "-m", "django", "test", "tests", "--noinput", "-v", "1"], env)
                        counts = re.findall(r"Ran (\d+) tests? in", log_path.read_text())
                        if not counts or int(counts[-1]) == 0:
                            raise RuntimeError("The test runner did not report a nonempty suite")
                        profile["tests"] = int(counts[-1])
                        profile["status"] = "passed"
                result["status"] = "passed"
            except Exception as error:
                result["status"] = "failed"
                result["error"] = str(error)
                if result["profiles"] and result["profiles"][-1]["status"] == "running":
                    result["profiles"][-1]["status"] = "failed"
        print(json.dumps(result), flush=True)
        return result

    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        results = list(executor.map(cell, CELLS))
    output = args.work / "matrix-results.json"
    output.write_text(json.dumps({"nova_source": str(args.nova_source) if args.nova_source else None, "database": "file-backed SQLite", "wheel": {"name": args.wheel.name, "sha256": hashlib.sha256(args.wheel.read_bytes()).hexdigest()}, "cells": results}, indent=2) + "\n")
    return 0 if all(r["status"] == "passed" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
