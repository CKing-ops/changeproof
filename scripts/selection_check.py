"""Week 10 exit check for test selection: do the selected subsets catch what the full suite catches?

    uv run python scripts/selection_check.py

For each of the 30 seeded bugs (tests/fixtures/equivalence/bugs.py), builds the program's suite
from the unchanged source, selects tests for the bug's changed lines by CP-SAT and by greedy, and
replays the full suite and both subsets on the mutant. Writes docs/weekly/week10-selection.json.
"""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

from changeproof.characterize import LocalRunner, characterize, replay
from changeproof.selection import changed_lines, select_tests, subset

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "synthetic"
REPORT = ROOT / "docs" / "weekly" / "week10-selection.json"


# PURPOSE: LOADS THE SEEDED BUG LIST
def load_bugs():
    spec = importlib.util.spec_from_file_location("bugs", ROOT / "tests" / "fixtures" / "equivalence" / "bugs.py")
    found = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(found)
    return found


# PURPOSE: RUNS EVERY BUG THROUGH FULL-SUITE AND SELECTED-SUBSET REPLAY AND WRITES THE REPORT
def main() -> int:
    bugs, runner = load_bugs(), LocalRunner()
    suites = {name: characterize(CORPUS / "batch" / f"{name}.cbl", CORPUS, runner)
              for name in ("FEECALC", "RISKSCR", "INTCALC")}
    rows = []
    with tempfile.TemporaryDirectory() as scratch:
        for bug in bugs.BUGS + bugs.HELD_OUT:
            base = (CORPUS / "batch" / f"{bug.program}.cbl").read_text()
            root = Path(scratch) / bug.id
            (root / "batch").mkdir(parents=True)
            (root / "batch" / f"{bug.program}.cbl").write_text(bugs.apply(base, bug))
            suite, lines = suites[bug.program], changed_lines(base, bugs.apply(base, bug))
            row = {"bug": bug.id, "program": bug.program, "changed_lines": sorted(lines),
                   "full": {"tests": len(suite["tests"]), "caught": bool(replay(suite, root, runner))}}
            for method in ("cp-sat", "greedy"):
                chosen = select_tests(suite, lines, method)
                row[method] = {"tests": len(chosen.selection), "optimal": chosen.optimal,
                               "caught": bool(replay(subset(suite, chosen.selection), root, runner))}
            rows.append(row)
    same = all(r[m]["caught"] == r["full"]["caught"] for r in rows for m in ("cp-sat", "greedy"))
    report = {"bugs": len(rows), "same_as_full_suite": same,
              "caught": {k: sum(r[k]["caught"] for r in rows) for k in ("full", "cp-sat", "greedy")},
              "test_runs": {k: sum(r[k]["tests"] for r in rows) for k in ("full", "cp-sat", "greedy")},
              "rows": rows}
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, indent=2))
    return 0 if same else 1


if __name__ == "__main__":
    sys.exit(main())
