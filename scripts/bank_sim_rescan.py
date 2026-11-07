"""Scans saved bank-simulation changes again with the engine as it is now (ADR 015).

    uv run python scripts/bank_sim_rescan.py --keep /mnt/project-files/changeproof/sim --out rescan.jsonl [--from-day 650]

Clones each bank's bundle (main and the rejected changes) into a scratch folder, checks out each
picked ledger row's commit and runs the same full-suite equivalence scan the simulation runs, with
fresh baselines. Prints and writes the old and new outcome of every row. Reads the keeping folder
only; needs GnuCOBOL; no network.
"""

import argparse
import json
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from changeproof.banksim.run import git, ledger, outcome
from changeproof.characterize import LocalRunner
from changeproof.equivalence import equivalence


# PURPOSE: CLONES ONE BANK'S BUNDLE WITH ITS REJECTED CHANGES INTO A SCRATCH FOLDER
def clone(bundle: Path, root: Path) -> None:
    subprocess.run(["git", "clone", "-q", str(bundle.resolve()), str(root)], check=True, capture_output=True)
    git(root, "fetch", "-q", str(bundle.resolve()), "refs/rejected/*:refs/rejected/*")


# PURPOSE: SCANS ONE LEDGER ROW'S COMMIT AGAIN AND RETURNS ITS OLD AND NEW OUTCOME
def rescan(row: dict, banks: Path) -> dict:
    started = time.monotonic()
    root = banks / row["bank"]
    with tempfile.TemporaryDirectory() as scratch:
        tree = Path(scratch) / "tree"
        git(root, "worktree", "add", "-q", "--detach", str(tree), row["commit"])
        found = equivalence(tree, "HEAD", scope="full-suite", runner=LocalRunner()).predicate
        git(root, "worktree", "remove", "--force", str(tree))
    return {k: row[k] for k in ("day", "date", "bank", "change", "kind", "commit", "provenance")} | {
        "was": row["outcome"], "verdict": found["verdict"], "now": outcome(row["kind"], found["verdict"]),
        "tests": found["summary"]["total"], "different": found["summary"]["different"],
        "differing_programs": sorted({t["target"]["name"] for t in found["tests"] if t["result"] == "different"}),
        "seconds": round(time.monotonic() - started)}


# PURPOSE: ROWS TO SCAN AGAIN: EVERY MISS, REFACTOR AND INTENDED CHANGE, PLUS THE FIRST CATCH OF EACH DEFECT AT EACH BANK
def picked(rows: list[dict]) -> list[dict]:
    first_catch = {}  # RENAME: (BANK, CHANGE ID) TO ITS FIRST CAUGHT ROW
    for row in rows:
        if row["outcome"] == "caught":
            first_catch.setdefault((row["bank"], row["change"]), row)
    chosen = {id(r) for r in first_catch.values()}
    return [r for r in rows if r["outcome"] == "missed" or r["kind"] != "defect" or id(r) in chosen]


# PURPOSE: CLONES THE BANKS, SCANS THE PICKED ROWS SIDE BY SIDE AND WRITES ONE LINE PER ROW
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep", required=True, help="the simulation's keeping folder")
    parser.add_argument("--out", required=True, help="JSON-lines file the results are written to")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--from-day", type=int, default=1, help="first simulated day to scan again")
    args = parser.parse_args()
    keep = Path(args.keep)
    rows = picked([r for r in ledger(keep) if r["day"] >= args.from_day])
    with tempfile.TemporaryDirectory() as scratch, ProcessPoolExecutor(args.workers) as pool, \
            open(args.out, "w", encoding="utf-8") as out:
        banks = Path(scratch)
        for bank in sorted({r["bank"] for r in rows}):
            clone(keep / "banks" / f"{bank}.bundle", banks / bank)
        for row in pool.map(rescan, rows, [banks] * len(rows)):
            out.write(json.dumps(row, sort_keys=True) + "\n")
            print(f"{row['date']} {row['bank']:15} {row['change']:25} {row['was']:10} -> {row['now']:10} "
                  f"{row['tests']} tests, {row['different']} different, {row['seconds']}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
