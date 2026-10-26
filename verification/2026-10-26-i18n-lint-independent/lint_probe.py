"""Independent scope and rejection checks for the configured Ruff gate."""
import json
from pathlib import Path
import subprocess
import sys
import tomllib

root, ruff, destination = map(Path, sys.argv[1:])
config = tomllib.loads((root / "pyproject.toml").read_text())["tool"]["ruff"]
pin = (root / "requirements-lint.txt").read_text().strip().split("==")[1]
assert config["required-version"] == "==" + pin
assert config["target-version"] == "py310"
results = []

def run(args, text=None):
    return subprocess.run([str(ruff), *args], cwd=root, input=text, capture_output=True, text=True)

positive = run(["check", ".", "--no-cache", "--output-format", "json"])
assert positive.returncode == 0, positive.stdout + positive.stderr
scope = run(["check", ".", "--show-files", "--no-cache"])
assert scope.returncode == 0, scope.stderr
observed = {Path(line).resolve().relative_to(root.resolve()).as_posix() for line in scope.stdout.splitlines()}
expected = {p.relative_to(root).as_posix() for directory in ("src", "tests", "scripts", "demo", "examples") for p in (root / directory).rglob("*.py")}
expected.update(("manage.py", "pyproject.toml"))
assert observed == expected, {"missing": sorted(expected - observed), "extra": sorted(observed - expected)}
results.append({"check": "exact current Python scope", "files": len(observed), "passed": True})
cases = [
    ("runtime undefined name", "src/nova_slider_captcha/probe.py", "def f():\n    return absent_name\n", "F821"),
    ("tests unused import", "tests/probe.py", "import math\n", "F401"),
    ("scripts bare except", "scripts/probe.py", "try:\n    print('test')\nexcept:\n    pass\n", "E722"),
    ("demo undefined name", "demo/probe.py", "print(absent_name)\n", "F821"),
    ("examples undefined name", "examples/probe.py", "print(absent_name)\n", "F821"),
    ("star import outside settings remains rejected", "src/nova_slider_captcha/probe.py", "from math import *\n", "F403"),
]
for name, path, source, code in cases:
    result = run(["check", "--no-cache", "--output-format", "json", "--stdin-filename", str(root / path), "-"], source)
    diagnostics = json.loads(result.stdout)
    assert result.returncode == 1 and code in {d["code"] for d in diagnostics}, (name, result.stdout, result.stderr)
    results.append({"check": name, "code": code, "exit": result.returncode, "passed": True})
syntax = run(["check", "--no-cache", "--output-format", "json", "--stdin-filename", str(root / "src/nova_slider_captcha/probe.py"), "-"], "def broken(:\n")
assert syntax.returncode == 1 and json.loads(syntax.stdout)
results.append({"check": "syntax error rejected", "exit": syntax.returncode, "passed": True})
version = run(["check", ".", "--config", 'required-version = "==0.0.0"'])
assert version.returncode != 0 and "required version" in version.stderr.lower(), version.stderr
results.append({"check": "wrong executable version rejected", "exit": version.returncode, "passed": True})
destination.write_text(json.dumps({"ruff": pin, "checks": results, "scope": sorted(observed)}, indent=2) + "\n")
print(json.dumps({"ruff": pin, "checks_passed": len(results), "source_files": len(observed)}))
