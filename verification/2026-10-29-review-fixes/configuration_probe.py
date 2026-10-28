"""Check CI pairing, DOM isolation and preservation of historical evidence."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    args.work.mkdir(parents=True, exist_ok=True)
    ci = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text())
    pairs = [(cell["python"], cell["django"], cell["pillow"]) for cell in ci["jobs"]["django"]["strategy"]["matrix"]["include"]]
    local = runpy.run_path(str(ROOT / "scripts/test_matrix.py"))["CELLS"]
    assert pairs == local
    assert "NOVA_TEST_DB" not in next(step for step in ci["jobs"]["web"]["steps"] if step.get("run") == "npm run test:dom")["env"]
    ignored = subprocess.check_output(["git", "check-ignore", "--no-index", ".mimosa/probe", ".video_agent/probe"], cwd=ROOT, text=True).splitlines()
    assert ignored == [".mimosa/probe", ".video_agent/probe"]
    historical = {}
    for name in ("verification/export-checks.json", "verification/matrix-results.json"):
        original = subprocess.check_output(["git", "show", "HEAD:" + name], cwd=ROOT)
        actual = (ROOT / name).read_bytes()
        assert original == actual
        historical[name] = hashlib.sha256(actual).hexdigest()
    # Exercise the actual bridge with a hostile inherited path and no stdin.
    # Its private default/derived paths must be selected before settings import.
    stale = args.work / "must-remain-absent/default.sqlite3"
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env["NOVA_TEST_DB"] = str(stale)
    code = """import io,json,runpy,sys
from pathlib import Path
sys.stdin=io.StringIO('')
runpy.run_path('scripts/dom_bridge.py')
from django.conf import settings
names={alias:Path(config['NAME']) for alias,config in settings.DATABASES.items()}
parent=names['default'].parent
assert parent.name.startswith('nova-slider-dom-')
assert all(path.parent==parent for path in names.values())
assert not parent.exists()
print(json.dumps({'aliases':list(names),'private_root_shared':True,'temporary_removed':True}))
"""
    bridge = json.loads(subprocess.check_output([sys.executable, "-c", code], cwd=ROOT, env=env, text=True))
    assert not stale.parent.exists()
    result = {"ci_pairs_match_local": pairs, "ignored_directories": ignored,
              "historical_files_unchanged_sha256": historical, "dom_isolation": bridge}
    (Path(__file__).parent / "configuration.json").write_text(json.dumps(result, indent=2) + "\n")
    print("CI pairs, ignored directories, historical files and DOM alias isolation passed")


if __name__ == "__main__":
    main()
