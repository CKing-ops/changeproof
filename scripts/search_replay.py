"""Re-scans recorded bank simulation commits with the engine as it is now, to measure a search change.

    uv run python scripts/search_replay.py <sim folder> [outcome ...]

The sim folder holds ledger.jsonl and banks/<bank>.bundle, as the scheduled simulation keeps them.
Each ledger row with one of the named outcomes (default: missed) is checked out from its bank's
bundle and scanned again with full-suite behavioural equivalence, from fresh characterization suites.
Writes docs/weekly/search-replay.json with the recorded and current verdicts. Needs GnuCOBOL; no network.
"""

import json
import subprocess
import sys
import tempfile
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from changeproof.characterize import LocalRunner
from changeproof.equivalence import equivalence

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "weekly" / "search-replay.json"
WORKERS = 4  # RENAME: COMMITS SCANNED AT ONCE


# PURPOSE: SCANS ONE RECORDED COMMIT AGAIN FROM ITS BANK'S BUNDLE AND RETURNS BOTH VERDICTS
def rescan(sim: Path, row: dict) -> dict:
    bundle = sim / "banks" / f"{row['bank']}.bundle"
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch) / row["bank"]
        subprocess.run(["git", "clone", "-q", str(bundle), str(root)], check=True)
        subprocess.run(["git", "-C", str(root), "fetch", "-q", str(bundle), "refs/rejected/*:refs/rejected/*"], check=True)
        subprocess.run(["git", "-C", str(root), "checkout", "-q", row["commit"]], check=True)
        found = equivalence(root, "HEAD", scope="full-suite", runner=LocalRunner()).predicate
    return {"bank": row["bank"], "day": row["day"], "change": row["change"], "kind": row["kind"],
            "commit": row["commit"], "provenance": row["provenance"], "recorded": row["outcome"],
            "recorded_verdict": row["engine"]["verdict"], "recorded_tests": row["engine"]["tests"],
            "verdict": found["verdict"], "tests": found["summary"]["total"]}


# PURPOSE: RESCANS EVERY LEDGER ROW WITH THE CHOSEN OUTCOMES AND WRITES THE COMPARISON
def main(sim: Path, outcomes: list[str]) -> dict:
    rows = [json.loads(line) for line in (sim / "ledger.jsonl").read_text().splitlines()]
    picked = [r for r in rows if r["outcome"] in outcomes]
    with ProcessPoolExecutor(WORKERS) as pool:
        scans = list(pool.map(rescan, [sim] * len(picked), picked))
    report = {"ledger_rows": len(rows), "outcomes": outcomes,
              "summary": {f"{recorded} -> {verdict}": n for (recorded, verdict), n in
                          sorted(Counter((s["recorded"], s["verdict"]) for s in scans).items())},
              "scans": scans}
    OUT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1]), sys.argv[2:] or ["missed"])["summary"], indent=2))
