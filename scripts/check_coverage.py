"""Fail closed on coverage scope and pure statement/branch maintenance floors.

Development/CI only; never imported by the CAPTCHA runtime. coverage report's
combined percentage is displayed for reference, not used as a branch metric.
"""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FORMS = "src/nova_slider_captcha/forms.py"
FLOORS = {"package": {"statements": 97, "branches": 95}, "forms": {"statements": 99, "branches": 97}}
COUNTS = ("covered_lines", "num_statements", "missing_lines", "excluded_lines", "covered_branches", "num_branches", "missing_branches")


def require(condition, message):
    if not condition:
        raise ValueError(message)


def check_report(data):
    version = (ROOT / "requirements-coverage.txt").read_text().strip().split("==")[1]
    require(data.get("meta", {}).get("branch_coverage") is True, "Branch measurement is required")
    require(data["meta"].get("version") == version, "Unexpected coverage.py version")
    files = data.get("files", {})
    expected = {path.relative_to(ROOT).as_posix() for path in (ROOT / "src/nova_slider_captcha").rglob("*.py")}
    require(bool(expected) and set(files) == expected, "Report must contain exactly this source package, including unexecuted files")
    sums = dict.fromkeys(COUNTS, 0)
    for name, info in files.items():
        counts = info["summary"]
        require(all(type(counts.get(key)) is int and counts[key] >= 0 for key in COUNTS), f"Invalid coverage counts: {name}")
        require(counts["excluded_lines"] == 0, f"Excluded source lines are not accepted: {name}")
        require(counts["covered_lines"] + counts["missing_lines"] == counts["num_statements"], f"Inconsistent statement counts: {name}")
        require(counts["covered_branches"] + counts["missing_branches"] == counts["num_branches"], f"Inconsistent branch counts: {name}")
        require(len(info["executed_lines"]) == counts["covered_lines"] and len(info["missing_lines"]) == counts["missing_lines"], f"Inconsistent statement detail: {name}")
        require(len(info["executed_branches"]) == counts["covered_branches"] and len(info["missing_branches"]) == counts["missing_branches"], f"Inconsistent branch detail: {name}")
        for key in COUNTS:
            sums[key] += counts[key]
    require(all(data.get("totals", {}).get(key) == value for key, value in sums.items()), "Totals do not match package files")
    results = {}
    for scope, counts in (("package", sums), ("forms", files[FORMS]["summary"])):
        statements, branches = counts["num_statements"], counts["num_branches"]
        require(statements > 0 and branches > 0, f"Empty {scope} measurement")
        require(counts["covered_lines"] * 100 >= FLOORS[scope]["statements"] * statements, f"{scope} statement coverage below {FLOORS[scope]['statements']}%")
        require(counts["covered_branches"] * 100 >= FLOORS[scope]["branches"] * branches, f"{scope} pure branch coverage below {FLOORS[scope]['branches']}%")
        results[scope] = {"statements_covered": counts["covered_lines"], "statements": statements, "statement_percent": counts["covered_lines"] * 100 / statements,
                          "branches_covered": counts["covered_branches"], "branches": branches, "branch_percent": counts["covered_branches"] * 100 / branches,
                          "combined_percent": (counts["covered_lines"] + counts["covered_branches"]) * 100 / (statements + branches), "floors": FLOORS[scope]}
    results["forms_missing_lines"] = files[FORMS]["missing_lines"]
    results["forms_missing_branches"] = files[FORMS]["missing_branches"]
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    args = parser.parse_args()
    try:
        result = check_report(json.loads(args.report.read_text()))
    except (OSError, ValueError, KeyError, TypeError, IndexError) as error:
        parser.exit(1, f"Coverage gate failed: {error}\n")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
