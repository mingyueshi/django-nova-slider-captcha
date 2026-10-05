"""Run source/wheel, native/Nova profiles against the exact Nova matrix.

Usage: python scripts/test_matrix.py --runtimes /path/to/uv-install-dir --nova-source /path/to/nova/django-theme/src --wheel /path/to/built.whl
All environment creation and reports stay in the selected --work directory.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys

CELLS = [("3.11.17", "5.2.17"), ("3.12.15", "5.2.17"), ("3.12.15", "6.0.8"), ("3.12.15", "6.1.1"), ("3.13.16", "6.1.1"), ("3.14.8", "5.2.17"), ("3.14.8", "6.1.1")]
ROOT = Path(__file__).resolve().parent.parent


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtimes", type=Path, required=True)
    parser.add_argument("--nova-source", type=Path, required=True)
    parser.add_argument("--wheel", type=Path, required=True)
    parser.add_argument("--work", type=Path, default=Path("/tmp/nova-slider-matrix"))
    parser.add_argument("--workers", type=int, default=3)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)

    def cell(spec):
        pyver, djver = spec
        directory = args.work / f"{pyver}-{djver}"
        directory.mkdir(exist_ok=True)
        interpreter = args.runtimes / f"cpython-{pyver}-linux-x86_64-gnu/bin/python3"
        log_path = directory / "run.log"
        result = {"python": pyver, "django": djver, "pillow": "12.2.0", "profiles": [], "log": str(log_path)}
        with log_path.open("w") as log:
            def run(command, env=None):
                log.write("$ " + " ".join(map(str, command)) + "\n")
                log.flush()
                subprocess.run(list(map(str, command)), cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
            try:
                run([interpreter, "-m", "venv", directory / "venv"])
                py = directory / "venv/bin/python"
                run([py, "-m", "pip", "install", "--disable-pip-version-check", f"Django=={djver}", "Pillow==12.2.0", "asgiref==3.12.1", "sqlparse==0.6.0", args.wheel])
                run([py, "-m", "pip", "check"])
                run([py, "-c", f"import platform, django, PIL; assert platform.python_version() == {pyver!r}; assert django.get_version() == {djver!r}; assert PIL.__version__ == '12.2.0'; print(platform.python_version(), django.get_version(), PIL.__version__)"])
                for mode in ("source", "wheel"):
                    for theme in ("native", "nova"):
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
    output = ROOT / "verification/matrix-results.json"
    output.write_text(json.dumps({"baseline_nova": "0.6.0", "database": "file-backed SQLite", "cells": results}, indent=2) + "\n")
    return 0 if all(r["status"] == "passed" for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
