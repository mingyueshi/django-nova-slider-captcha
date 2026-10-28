"""Run the actual Django check CLI with isolated invalid engine settings.

Run from the repository root with the candidate package installed:
python verification/2026-10-29-session-engine-followup/check_command.py --work /new/private/directory
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    work = args.work.resolve()
    work.mkdir(parents=True, exist_ok=True)
    (work / "probe_settings.py").write_text('''import json,os,secrets
SECRET_KEY=secrets.token_hex(32)
INSTALLED_APPS=["nova_slider_captcha"]
MIDDLEWARE=["django.contrib.sessions.middleware.SessionMiddleware","django.middleware.csrf.CsrfViewMiddleware"]
ROOT_URLCONF="nova_slider_captcha.urls"
DATABASES={"default":{"ENGINE":"django.db.backends.sqlite3","NAME":os.environ["NOVA_PROBE_DB"]}}
SESSION_ENGINE=json.loads(os.environ["NOVA_PROBE_ENGINE"])
DEFAULT_AUTO_FIELD="django.db.models.BigAutoField"
USE_TZ=True
''')
    results = []
    for name, engine in (("missing_module", "tests.not_a_session_engine"), ("missing_store", "types"), ("nonclass_store", "tests.test_session_backend"), ("empty_path", ""), ("nonstring_path", None)):
        env = os.environ.copy()
        env.update(DJANGO_SETTINGS_MODULE="probe_settings", PYTHONPATH=os.pathsep.join((str(work), str(ROOT))),
                   NOVA_PROBE_ENGINE=json.dumps(engine), NOVA_PROBE_DB=str(work / (name + ".sqlite3")))
        command = [sys.executable, "-m", "django", "check"]
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, timeout=30)
        output = result.stdout + result.stderr
        assert result.returncode == 1 and "nova_slider_captcha.E008" in output and "Traceback" not in output, output
        assert not (work / (name + ".sqlite3")).exists()
        results.append({"case": name, "exit_code": result.returncode, "output": output})
    (Path(__file__).parent / "check-command.json").write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"cases": len(results), "status": "passed"}))


if __name__ == "__main__":
    main()
