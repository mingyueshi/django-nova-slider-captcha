"""Local read-only-runtime verification; no service startup or package changes."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
RUNTIMES = {"py310": "/tmp/nova-slider-implementation-20261026-py310/bin/python", "py312": "/tmp/nova-slider-review-20261026/bin/python"}
LABEL = sys.argv[1] if len(sys.argv) > 1 else "complete"


def check_profile(name, python):
    env = os.environ.copy()
    env.update(PYTHONPATH="src:.", DJANGO_SETTINGS_MODULE="tests.settings", NOVA_TEST_DB=f"/tmp/nova-slider-integration-{name}-20261026.sqlite3", PYTHONDONTWRITEBYTECODE="1")
    commands = [
        [python, "-c", "import platform,django,PIL,sqlite3; print(platform.python_version(),django.get_version(),PIL.__version__,sqlite3.sqlite_version)"],
        [python, "-m", "django", "check"],
        [python, "-m", "django", "makemigrations", "nova_slider_captcha", "--check", "--dry-run"],
        [python, "-m", "django", "test", "tests", "--noinput", "-v", "1"],
        ["uv", "pip", "check", "--python", python],
    ]
    with (OUT / f"{name}-{LABEL}.log").open("x") as log:
        for command in commands:
            log.write("$ " + " ".join(command) + "\n")
            log.flush()
            subprocess.run(command, cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
    return {"runtime": name, "python": python, "status": "passed"}


if __name__ == "__main__":
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda item: check_profile(*item), RUNTIMES.items()))
    with (OUT / f"python-{LABEL}-results.json").open("x") as result:
        result.write(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results))
