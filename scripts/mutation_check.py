"""Week 9 mutation check, end to end: each seeded bug is a commit, and `equivalence` runs on it.

    uv run python scripts/mutation_check.py

Builds the Week 9 seed repository's import commit, then one branch per bug from
tests/fixtures/equivalence/bugs.py. For each bug commit it runs the full-suite equivalence check
(baselines kept between runs) and records whether the verdict is not-equivalent and which tests
differed. Writes docs/weekly/week09-mutation.json.
"""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

from changeproof.characterize import LocalRunner
from changeproof.equivalence import equivalence

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "equivalence"
REPORT = ROOT / "docs" / "weekly" / "week09-mutation.json"
TARGET = 0.85  # RENAME: SHARE OF BUGS THE EXIT CHECK NEEDS CAUGHT
KILL = 0.60  # RENAME: SHARE BELOW WHICH THE ROADMAP'S KILL GATE TRIGGERS


# PURPOSE: LOADS A FIXTURE MODULE BY FILE NAME
def fixture(name: str):
    spec = importlib.util.spec_from_file_location(name, FIXTURES / f"{name}.py")
    found = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(found)
    return found


# PURPOSE: COMMITS EACH BUG ON ITS OWN BRANCH FROM THE IMPORT, RUNS EQUIVALENCE ON IT AND WRITES THE REPORT
def main() -> int:
    seeds, bugs = fixture("seed"), fixture("bugs")
    rows = []
    with tempfile.TemporaryDirectory() as scratch:
        root, kept = Path(scratch) / "repo", Path(scratch) / "baselines"
        kept.mkdir()
        base = seeds.seed(root)["base"]
        for n, bug in enumerate(bugs.BUGS, 10):
            seeds.run(root, "checkout", "-q", "-b", f"bug-{bug.id}", base)
            path = root / "src" / "batch" / f"{bug.program}.cbl"
            path.write_text(bugs.apply(path.read_text(), bug))
            sha = seeds.commit(root, seeds.AUTHOR, n % 28 + 1, f"LOAN-{n}: {bug.mistake}")
            p = equivalence(root, sha, scope="full-suite", runner=LocalRunner(), baselines=kept).predicate
            different = sorted({t["target"]["name"] for t in p["tests"] if t["result"] == "different"})
            rows.append({"bug": bug.id, "program": bug.program, "mistake": bug.mistake,
                         "change": f"{bug.old} -> {bug.new}", "verdict": p["verdict"],
                         "caught": p["verdict"] == "not-equivalent", "programs_differing": different,
                         "tests_differing": p["summary"]["different"], "tests_run": p["summary"]["total"]})
            print(f"{bug.id:3} {bug.program:8} {p['verdict']:15} {p['summary']['different']:3}/{p['summary']['total']}",
                  file=sys.stderr)
    caught = sum(r["caught"] for r in rows)
    report = {"bugs": len(rows), "caught": caught, "share": round(caught / len(rows), 4), "target": TARGET,
              "kill_gate": KILL, "rows": rows}
    REPORT.write_text(json.dumps(report, indent=1) + "\n")
    print(f"caught {caught}/{len(rows)} ({caught / len(rows):.0%}); target {TARGET:.0%}, kill gate under {KILL:.0%}")
    return 0 if caught / len(rows) >= TARGET else 1


if __name__ == "__main__":
    sys.exit(main())
