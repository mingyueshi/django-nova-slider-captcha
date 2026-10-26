"""Negative checks against an actual measured report, not a fabricated pass."""
import argparse
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    measured = json.loads(args.report.read_text())
    gate = [sys.executable, str(ROOT / "scripts/check_coverage.py")]
    subprocess.run([*gate, str(args.report)], cwd=ROOT, check=True, capture_output=True)
    names = ("empty", "no_branch", "wrong_package", "missing_forms", "wrong_version", "inconsistent_totals", "zero_branches", "excluded_lines", "package_branch_floor", "forms_branch_floor", "package_statement_floor", "forms_statement_floor")
    cases = {name: copy.deepcopy(measured) for name in names}
    cases["empty"] = {}
    cases["no_branch"]["meta"]["branch_coverage"] = False
    cases["wrong_package"]["files"] = {"other_package/forms.py": next(iter(measured["files"].values()))}
    cases["missing_forms"]["files"].pop("src/nova_slider_captcha/forms.py")
    cases["wrong_version"]["meta"]["version"] = "0.0"
    cases["inconsistent_totals"]["totals"]["covered_lines"] = 0
    for info in cases["zero_branches"]["files"].values():
        info["summary"].update(covered_branches=0, num_branches=0, missing_branches=0)
        info["executed_branches"], info["missing_branches"] = [], []
    for key in ("covered_branches", "num_branches", "missing_branches"):
        cases["zero_branches"]["totals"][key] = 0
    cases["excluded_lines"]["files"]["src/nova_slider_captcha/forms.py"]["summary"]["excluded_lines"] = 1
    # Keep each lowered report internally consistent. The package branch case
    # can still have >97% combined coverage; it must fail the pure branch floor.
    reasons = {}
    for name, file, kind, scope in (
        ("package_branch_floor", "src/nova_slider_captcha/views.py", "branches", "package"),
        ("forms_branch_floor", "src/nova_slider_captcha/forms.py", "branches", "forms"),
        ("package_statement_floor", "src/nova_slider_captcha/views.py", "lines", "package"),
        ("forms_statement_floor", "src/nova_slider_captcha/forms.py", "lines", "forms"),
    ):
        low = cases[name]
        info = low["files"][file]
        total = low["totals"] if scope == "package" else info["summary"]
        floor = {("package", "branches"): 95, ("forms", "branches"): 97,
                 ("package", "lines"): 97, ("forms", "lines"): 99}[scope, kind]
        denominator = total["num_branches" if kind == "branches" else "num_statements"]
        amount = total["covered_" + kind] - (floor * denominator + 99) // 100 + 1
        assert amount > 0 and amount <= len(info["executed_" + kind])
        info["missing_" + kind] += info["executed_" + kind][:amount]
        info["executed_" + kind] = info["executed_" + kind][amount:]
        for counts in (info["summary"], low["totals"]):
            counts["covered_" + kind] -= amount
            counts["missing_" + kind] += amount
        reasons[name] = f"{scope} {'pure branch' if kind == 'branches' else 'statement'} coverage below"
    with tempfile.TemporaryDirectory(prefix="nova-coverage-negative-") as directory:
        for name, data in cases.items():
            path = Path(directory) / f"{name}.json"
            path.write_text(json.dumps(data))
            result = subprocess.run([*gate, str(path)], cwd=ROOT, capture_output=True, text=True)
            if result.returncode == 0:
                raise AssertionError(f"Invalid report passed: {name}")
            if name in reasons and reasons[name] not in result.stderr:
                raise AssertionError(f"Wrong rejection reason for {name}: {result.stderr}")
    print(json.dumps({"valid_measured_report": "passed", "rejected": list(cases)}))


if __name__ == "__main__":
    main()
