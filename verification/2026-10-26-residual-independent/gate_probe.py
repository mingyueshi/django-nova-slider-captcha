"""Exercise real coverage floors with internally consistent missing branches."""
import copy
import importlib.util
import json
from pathlib import Path
import sys

root, report, output = map(Path, sys.argv[1:])
spec = importlib.util.spec_from_file_location("coverage_gate_under_review", root / "scripts/check_coverage.py")
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)
measured = json.loads(report.read_text())
gate.check_report(measured)
forms = "src/nova_slider_captcha/forms.py"


def lose(data, name, kind, count):
    info = data["files"][name]
    detail = "lines" if kind == "statements" else "branches"
    covered = "covered_lines" if kind == "statements" else "covered_branches"
    missing = "missing_lines" if kind == "statements" else "missing_branches"
    moved = info["executed_" + detail][:count]
    assert len(moved) == count
    info["executed_" + detail] = info["executed_" + detail][count:]
    info["missing_" + detail] += moved
    for summary in (info["summary"], data["totals"]):
        summary[covered] -= count
        summary[missing] += count
        # Stored percentages are intentionally misleading: the gate must compute
        # from counts, not trust rounded/display percentages supplied by JSON.
        summary["percent_covered"] = 100


cases = []
for scope, kind, count, expected in (
    ("forms", "branches", 2, "forms pure branch coverage"),
    ("forms", "statements", 2, "forms statement coverage"),
    ("package", "branches", 5, "package pure branch coverage"),
    ("package", "statements", 11, "package statement coverage"),
):
    data = copy.deepcopy(measured)
    key = "covered_branches" if kind == "branches" else "covered_lines"
    name = forms if scope == "forms" else next(name for name, info in data["files"].items()
                                               if name != forms and info["summary"][key] >= count)
    lose(data, name, kind, count)
    try:
        gate.check_report(data)
    except ValueError as error:
        assert expected in str(error), str(error)
        cases.append({"case": scope + "_" + kind, "rejected": True, "reason": str(error)})
    else:
        raise AssertionError("Low coverage accepted: " + expected)

for case in ("empty_report", "no_branch_measurement", "missing_unexecuted_module", "foreign_package"):
    data = copy.deepcopy(measured)
    if case == "empty_report":
        data = {}
    elif case == "no_branch_measurement":
        data["meta"]["branch_coverage"] = False
    elif case == "missing_unexecuted_module":
        data["files"].pop("src/nova_slider_captcha/__init__.py")
    else:
        data["files"]["foreign_package/forms.py"] = data["files"].pop(forms)
    try:
        gate.check_report(data)
    except ValueError as error:
        cases.append({"case": case, "rejected": True, "reason": str(error)})
    else:
        raise AssertionError("Invalid report accepted: " + case)

output.write_text(json.dumps({"valid_report_passed": True, "rejected": cases}, indent=2) + "\n")
print(json.dumps(cases))
