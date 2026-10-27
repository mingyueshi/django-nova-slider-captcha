"""Independent stable-candidate checks; output remains task-isolated."""
import json
import os
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parent
repo = Path('/Users/apple/Documents/GitHub/django-nova-slider-captcha')
python = '/var/folders/kq/dz44fm994nz94zw2dfqnz_g00000gn/T/nova-slider-residual-independent-20261026-ew8b5ibl/ci-coverage-env/bin/python'
lint = '/tmp/nova-slider-i18n-independent-20261026-cGZx5G/lint-env/bin/ruff'
mode = sys.argv[1]
out = root / mode
out.mkdir(exist_ok=False)
env = {**os.environ, 'DJANGO_SETTINGS_MODULE': 'tests.settings', 'PYTHONPATH': 'src:.', 'NOVA_TEST_DB': str(out / 'test.sqlite3'), 'COVERAGE_FILE': str(out / '.coverage'), 'NOVA_PYTHON': python, 'NOVA_DOM_REPORT': str(out / 'dom.json')}
if mode == 'coverage':
    commands = [
        [python, '-c', "import platform,django,PIL,coverage,nova_slider_captcha; print(platform.python_version(),django.get_version(),PIL.__version__,coverage.__version__,nova_slider_captcha.__file__)"],
        [python, '-m', 'coverage', 'run', '-m', 'django', 'test', 'tests', '--noinput', '-v', '1'],
        [python, '-m', 'coverage', 'combine', '--keep'],
        [python, '-m', 'coverage', 'json', '--pretty-print', '-o', str(out / 'coverage.json')],
        [python, '-m', 'coverage', 'report'],
        [python, 'scripts/check_coverage.py', str(out / 'coverage.json')],
        [python, 'scripts/test_coverage_gate.py', str(out / 'coverage.json')],
    ]
elif mode == 'web':
    commands = [[lint, 'check', '.'], ['node', '--version'], ['npm', 'test'], ['npm', 'run', 'test:dom']]
else:
    raise ValueError(mode)
summary = []
for index, command in enumerate(commands):
    run = subprocess.run(command, cwd=repo, env=env, capture_output=True, text=True)
    log = '$ ' + ' '.join(command) + chr(10) + run.stdout + run.stderr
    (out / f'{index:02}.log').write_text(log)
    summary.append({'command': command, 'returncode': run.returncode})
    (out / 'commands.json').write_text(json.dumps(summary, indent=2) + chr(10))
    print(mode, index, 'passed' if run.returncode == 0 else 'FAILED', flush=True)
    if run.returncode:
        print(log)
        sys.exit(run.returncode)
