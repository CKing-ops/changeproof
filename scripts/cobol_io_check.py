"""Runs the COBOL behaviour check on every CardDemo program in app/cbl and on bugs planted in its posting job.

    uv run python scripts/cobol_io_check.py

Each program is characterized (subprograms through their linkage, batch jobs on generated files) or listed
with why it cannot be. Then each planted bug is put into a copy of CBTRN02C, the daily transaction posting
job, and its suite is replayed against the copy. Writes docs/weekly/cobol-io-carddemo.json. Needs GnuCOBOL;
no network.
"""

import json
import shutil
import sys
import tempfile
import time
from pathlib import Path

from changeproof.adapters.cobol.gnucobol import LocalRunner
from changeproof.characterize import characterize, replay

ROOT = Path(__file__).resolve().parent.parent
CARDDEMO = ROOT / "corpus" / "carddemo"
COPYBOOKS = ["app/cpy"]
OUT = ROOT / "docs" / "weekly" / "cobol-io-carddemo.json"
POSTING = "app/cbl/CBTRN02C.cbl"
PLANTED = [  # RENAME: BUGS PLANTED IN THE POSTING JOB: TEXT, REPLACEMENT
    ("ADD DALYTRAN-AMT  TO ACCT-CURR-BAL", "SUBTRACT DALYTRAN-AMT FROM ACCT-CURR-BAL"),
    ("IF DALYTRAN-AMT >= 0", "IF DALYTRAN-AMT < 0"),
    ("- ACCT-CURR-CYC-DEBIT", "+ ACCT-CURR-CYC-DEBIT"),
    ("IF ACCT-CREDIT-LIMIT >= WS-TEMP-BAL", "IF ACCT-CREDIT-LIMIT > WS-TEMP-BAL"),
    ("IF ACCT-EXPIRAION-DATE >= DALYTRAN-ORIG-TS (1:10)", "IF ACCT-EXPIRAION-DATE > DALYTRAN-ORIG-TS (1:10)"),
    ("MOVE 4 TO RETURN-CODE", "MOVE 0 TO RETURN-CODE"),
]


# PURPOSE: CHARACTERIZES ONE PROGRAM AND SUMS UP ITS SUITE, OR SAYS WHY IT COULD NOT
def check(path: Path, runner: LocalRunner) -> tuple[dict, dict | None]:
    started = time.monotonic()
    try:
        suite = characterize(path, CARDDEMO, runner, COPYBOOKS)
    except (ValueError, RuntimeError) as exc:
        return {"reason": str(exc).splitlines()[0]}, None
    outcomes = sum(len(c["covered"]) for c in suite["conditions"])
    return {"tests": len(suite["tests"]), "runs": suite["runs"],
            "outcomes_reached": outcomes, "outcomes": 2 * len(suite["conditions"]),
            "return_codes": sorted({t["rc"] for t in suite["tests"]}),
            "seconds": round(time.monotonic() - started)}, suite


# PURPOSE: CHECKS EVERY PROGRAM, THEN THE PLANTED BUGS, AND KEEPS THE RESULTS
def main() -> int:
    runner = LocalRunner()
    found = {"corpus": "aws-samples/aws-mainframe-modernization-carddemo", "runner": runner.describe(),
             "programs": {}, "planted": []}
    suites = {}
    for path in sorted((CARDDEMO / "app" / "cbl").iterdir(), key=lambda p: p.name.upper()):
        if path.suffix.lower() != ".cbl":
            continue
        result, suites[path.stem] = check(path, runner)
        found["programs"][path.stem] = result
        print(path.stem, result, flush=True)
    suite = suites["CBTRN02C"]
    for old, new in PLANTED:
        with tempfile.TemporaryDirectory() as scratch:
            copy = Path(scratch) / "carddemo"
            shutil.copytree(CARDDEMO / "app" / "cpy", copy / "app" / "cpy")
            (copy / POSTING).parent.mkdir(parents=True)
            text = (CARDDEMO / POSTING).read_text(encoding="utf-8")
            if old not in text:
                print(f"planted text not found: {old}", file=sys.stderr)
                return 1
            (copy / POSTING).write_text(text.replace(old, new, 1), encoding="utf-8")
            differences = replay(suite, copy, runner, COPYBOOKS)
        found["planted"].append({"from": old, "to": new, "caught": bool(differences),
                                 "tests_differing": len({d["test"] for d in differences}),
                                 "fields_differing": sorted({d["field"] for d in differences})})
        print(f"{old} -> {new}: {len(differences)} differences", flush=True)
    OUT.write_text(json.dumps(found, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
