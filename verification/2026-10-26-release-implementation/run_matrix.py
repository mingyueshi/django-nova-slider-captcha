"""Local paired source/wheel matrix. Uses only implementation-owned venvs."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
WHEEL = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/nova-slider-release-impl-candidate-20261026/nova_slider_captcha-0.3.0-py3-none-any.whl")
LABEL = sys.argv[2] if len(sys.argv) > 2 else "final"
CELLS = [("py310", "dj5217", "3.10.20", "5.2.17"), ("py312", "dj5217", "3.12.14", "5.2.17"), ("py312", "dj612", "3.12.14", "6.1.2"), ("py313", "dj612", "3.13.12", "6.1.2")]


def cell(spec):
    py, dj, py_version, dj_version = spec
    python = f"/tmp/nova-slider-release-impl-{py}-{dj}-20261026/bin/python"
    record = {"python": py_version, "django": dj_version, "profiles": []}
    log_path = OUT / f"{py}-{dj}-{LABEL}.log"
    with log_path.open("x") as log:
        def run(command, env):
            log.write("$ " + " ".join(map(str, command)) + "\n")
            log.flush()
            subprocess.run(list(map(str, command)), cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        for mode in ("source", "wheel"):
            env = os.environ.copy()
            env.update(PYTHONPATH="src:." if mode == "source" else ".", DJANGO_SETTINGS_MODULE="tests.settings", PYTHONDONTWRITEBYTECODE="1", NOVA_TEST_DB=f"/tmp/nova-slider-release-impl-{py}-{dj}-{mode}.sqlite3")
            if mode == "wheel":
                run(["uv", "pip", "install", "--python", python, "--no-deps", WHEEL], env)
            expected = str((ROOT / "src").resolve()) if mode == "source" else str(Path(python).parents[1].resolve())
            run([python, "-c", f"import pathlib,platform,django,PIL,nova_slider_captcha; p=pathlib.Path(nova_slider_captcha.__file__).resolve(); print(platform.python_version(),django.get_version(),PIL.__version__,p); assert platform.python_version()=={py_version!r}; assert django.get_version()=={dj_version!r}; assert PIL.__version__=='12.2.0'; assert str(p).startswith({expected!r})"], env)
            run([python, "-m", "django", "check"], env)
            run([python, "-m", "django", "makemigrations", "nova_slider_captcha", "--check", "--dry-run"], env)
            run([python, "-m", "django", "test", "tests", "--noinput", "-v", "1"], env)
            run(["uv", "pip", "check", "--python", python], env)
            counts = re.findall(r"Ran (\d+) tests? in", log_path.read_text())
            if not counts:
                raise RuntimeError("No test count")
            record["profiles"].append({"mode": mode, "tests": int(counts[-1]), "status": "passed"})
    print(json.dumps(record), flush=True)
    return record


if __name__ == "__main__":
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(cell, CELLS))
    with (OUT / f"matrix-{LABEL}-results.json").open("x") as output:
        json.dump({"wheel": {"path": str(WHEEL), "sha256": hashlib.sha256(WHEEL.read_bytes()).hexdigest()}, "cells": results}, output, indent=2)
        output.write("\n")
