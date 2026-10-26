"""Run source and the same wheel in explicit, isolated Python environments.

Usage: python matrix.py WORKSPACE ENVIRONMENTS_JSON WHEEL OUTPUT_DIRECTORY
Environment entries contain name, python (absolute executable), and versions.
"""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

workspace, manifest, wheel, output = map(Path, sys.argv[1:])
rows = json.loads(manifest.read_text())
output.mkdir(parents=True, exist_ok=False)


def run_row(row):
    name, python = row["name"], row["python"]
    records = []
    for mode in ("source", "wheel"):
        env = os.environ.copy()
        env.update(DJANGO_SETTINGS_MODULE="tests.settings", PYTHONPATH="src:." if mode == "source" else ".",
                   NOVA_TEST_DB=str(output / f"{name}-{mode}.sqlite3"))
        commands = []
        if mode == "wheel":
            commands.append(["uv", "pip", "install", "--python", python, "--no-deps", "--reinstall-package", "nova-slider-captcha", str(wheel)])
        commands.extend([
            ["uv", "pip", "check", "--python", python],
            [python, "-c", "import pathlib,nova_slider_captcha; p=pathlib.Path(nova_slider_captcha.__file__).resolve(); "
             "print(p); assert p.is_relative_to(pathlib.Path('src').resolve())" + ("" if mode == "source" else " is False")],
            [python, "-m", "django", "check"],
            [python, "-m", "django", "makemigrations", "nova_slider_captcha", "--check", "--dry-run"],
            [python, "-m", "django", "test", "tests", "--noinput", "-v", "1"],
        ])
        log = []
        for command in commands:
            proc = subprocess.run(command, cwd=workspace, env=env, capture_output=True, text=True)
            log.append("$ " + " ".join(command) + "\n" + proc.stdout + proc.stderr)
            if proc.returncode:
                (output / f"{name}-{mode}.log").write_text("\n".join(log))
                raise RuntimeError(f"{name}/{mode}: " + log[-1])
        (output / f"{name}-{mode}.log").write_text("\n".join(log))
        records.append({"mode": mode, "status": "passed"})
        print(name, mode, "passed", flush=True)
    return {"name": name, "versions": row["versions"], "checks": records}


with ThreadPoolExecutor(max_workers=3) as pool:
    results = list(pool.map(run_row, rows))
(output / "summary.json").write_text(json.dumps({
    "wheel": wheel.name,
    "wheel_sha256": hashlib.sha256(wheel.read_bytes()).hexdigest(),
    "matrix": results,
    "limitations": ["Local SQLite only", "No remote CI, publication, or production checks"],
}, indent=2) + "\n")
