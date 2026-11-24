"""Scans every Cash Account change at the bank that runs IBM's public COBOL (ADR 017).

    uv run python scripts/bank_sim_public.py --out docs/weekly/banksim-cash-account.json

Each change is committed on its own simulated day against the same imported estate, scanned and
scored. Needs GnuCOBOL for the bank's own programs; no network.
"""

import argparse
import json
import tempfile
from collections import Counter
from pathlib import Path

from changeproof.banksim.public import catalogue, scan


# PURPOSE: SCANS THE WHOLE CATALOGUE ONCE AND WRITES THE ROWS WITH THEIR TOTALS
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as scratch:
        rows = [scan(Path(scratch), day, only=change.id) for day, change in enumerate(catalogue(), 1)]
    totals = {key: dict(Counter(r[key]["outcome"] if key != "outcome" else r[key] for r in rows))
              for key in ("outcome", "impact", "governance")}
    Path(args.out).write_text(json.dumps({"totals": totals, "rows": rows}, indent=1) + "\n", encoding="utf-8")
    print(json.dumps(totals))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
