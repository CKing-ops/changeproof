"""Sums up a stretch of the bank simulation: outcomes by kind, program and class of change, plus the business.

    uv run python scripts/bank_report.py /mnt/project-files/changeproof/sim-diverse --from-day 1280

Every number is counted from the folder's ledger.jsonl and operations.jsonl (ADR 014, ADR 016).
"""

import argparse
import json
import sys
from collections import Counter
from decimal import Decimal
from pathlib import Path

CLASSES = {  # RENAME: CHANGE ID PATTERN TO THE WEAK SPOT IT AIMS AT
    "rounding": ("-truncate",),
    "boundary": ("-strict", "-boundary"),
    "data-division": ("-precision", "-narrow"),
}


# PURPOSE: THE WEAK SPOT A CHANGE AIMS AT, BY ITS ID
def kind_of(change: str) -> str:
    return next((name for name, marks in CLASSES.items() if any(m in change for m in marks)), "logic")


# PURPOSE: OUTCOME COUNTS PER GROUP OF LEDGER ROWS
def tally(rows: list[dict], key) -> dict:
    found: dict[str, Counter] = {}
    for row in rows:
        found.setdefault(key(row), Counter())[row["outcome"]] += 1
    return {k: dict(v) for k, v in sorted(found.items())}


# PURPOSE: THE ROWS OF A JSON-LINES FILE
def lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


# PURPOSE: READS THE LEDGERS, KEEPS THE ASKED-FOR DAYS AND PRINTS ONE JSON SUMMARY
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("keep")
    parser.add_argument("--from-day", type=int, default=1)
    args = parser.parse_args()
    keep = Path(args.keep)
    rows = [r for r in lines(keep / "ledger.jsonl") if r["day"] >= args.from_day]
    days = [o for o in lines(keep / "operations.jsonl") if o["day"] >= args.from_day and "loans" in o]
    misses = [{"day": r["day"], "bank": r["bank"], "change": r["change"], "kind": r["kind"],
               "where": f"{r['provenance']['file']}:{r['provenance']['line']}", "tests": r["engine"]["tests"],
               "live_traffic_different": r["traffic"]["different"], "live_runs": r["traffic"]["runs"]}
              for r in rows if r["outcome"] in ("missed", "false-alarm", "inconclusive")]

    # PURPOSE: A MONEY TOTAL OVER THE DAYS FOR ONE PART OF THE BUSINESS, PER CURRENCY
    def money(part: str, field: str) -> dict[str, str]:
        found: dict[str, Decimal] = {}
        for o in days:
            currency = "EUR" if o["market"] == "eu-dora" else "USD"
            found[currency] = found.get(currency, Decimal(0)) + Decimal(o[part][field])
        return {k: str(v) for k, v in sorted(found.items())}

    print(json.dumps({
        "days": sorted({r["day"] for r in rows}), "changes": len(rows), "distinct_changes": len({r["change"] for r in rows}),
        "by_kind": tally(rows, lambda r: r["kind"]),
        "by_market": tally(rows, lambda r: r["market"]),
        "by_program": tally(rows, lambda r: Path(r["provenance"]["file"]).stem),
        "by_class": tally([r for r in rows if r["kind"] == "defect"], lambda r: kind_of(r["change"])),
        "by_change": tally(rows, lambda r: r["change"]),
        "governance": dict(Counter(r["governance"]["outcome"] for r in rows)),
        "governance_paths": dict(Counter(r["truth"]["governance"] for r in rows)),
        "merged_defects": sum(r["merged"] and r["kind"] == "defect" for r in rows),
        "seconds_per_scan": round(sum(r["seconds"] for r in rows) / max(len(rows), 1), 1),
        "tests_per_scan": round(sum(r["engine"]["tests"] for r in rows) / max(len(rows), 1), 1),
        "wrong": misses,
        "business": {"bank_days": len(days),
                     "postings": sum(o["postings"] for o in days), "payments": sum(o["payments"] for o in days),
                     "loan_installments": sum(o["loans"]["installments"] for o in days),
                     "loan_interest": money("loans", "interest"), "late_fees": money("loans", "late_fees"),
                     "fx_conversions": sum(o["fx"]["conversions"] for o in days),
                     "fx_converted": money("fx", "converted"), "fx_fees": money("fx", "fees"),
                     "cash_transactions": sum(o["cash"]["transactions"] for o in days),
                     "cash_reports": sum(o["cash"]["reported"] for o in days),
                     "structuring_alerts": sum(o["cash"]["structuring_alerts"] for o in days)},
    }, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
