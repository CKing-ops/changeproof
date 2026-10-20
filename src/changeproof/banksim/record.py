"""The one-page record of the bank simulation, rebuilt from its ledgers after every simulated day.

Every number on the page is counted from ledger.jsonl and operations.jsonl, so the page can be
regenerated from them at any time and never says more than they do.
"""

from collections import Counter
from decimal import Decimal
from pathlib import Path

MARKETS = (("general", "US banks (general)"), ("eu-dora", "EU banks (eu-dora)"))  # RENAME: MARKET TO PAGE COLUMN
RECENT = 15  # RENAME: MISSES AND FALSE ALARMS LISTED ON THE PAGE


# PURPOSE: "A OF B (P%)", OR A DASH WHEN THERE IS NOTHING TO COUNT
def share(part: int, whole: int) -> str:
    return f"{part} of {whole} ({100 * part / whole:.0f}%)" if whole else "-"


# PURPOSE: THE ENGINE'S HEADLINE COUNTS FOR A GROUP OF LEDGER ROWS, ONE LINE PER MEASURE
def measures(rows: list[dict]) -> dict[str, str]:
    kinds = Counter(r["kind"] for r in rows)
    out = Counter(r["outcome"] for r in rows)
    approvals = Counter(r["governance"]["outcome"] for r in rows)
    misses = [r for r in rows if r["outcome"] == "missed" and "traffic" in r]
    return {
        "Defects caught": share(sum(r["outcome"] == "caught" for r in rows), kinds["defect"]),
        "Intended changes confirmed": share(sum(r["outcome"] == "confirmed" for r in rows), kinds["intended"]),
        "Refactors proven equivalent": share(out["proven"], kinds["refactor"]),
        "False alarms": str(out["false-alarm"]),
        "Inconclusive": str(out["inconclusive"]),
        "Approval gaps flagged": share(approvals["flagged"], approvals["flagged"] + approvals["missed"]),
        "Approvals wrongly flagged": str(approvals["false-flag"]),
        "Misses the day's live traffic showed": share(sum(r["traffic"]["different"] > 0 for r in misses), len(misses)),
    }


# PURPOSE: A MARKDOWN TABLE FROM A HEADER AND ROWS
def table(header: list[str], body: list[list[str]]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + ["| " + " | ".join(r) + " |" for r in body]


# PURPOSE: A MONEY TOTAL WITH THOUSANDS SEPARATORS
def amount(value: Decimal | str) -> str:
    return f"{Decimal(value):,.2f}"


# PURPOSE: THE PROGRAM A LEDGER ROW'S CHANGE WAS MADE IN
def program(row: dict) -> str:
    return Path(row["provenance"]["file"]).stem


# PURPOSE: THE WHOLE PAGE: HEADLINE, BY MARKET, BY PROGRAM, EACH BANK'S LATEST DAY, BY SIMULATED MONTH, RECENT MISSES
def page(rows: list[dict], operations: list[dict], updated: str = "") -> str:
    if not rows:
        return "# Bank simulation record\n\nNo simulated days yet.\n"
    last = max(r["day"] for r in rows)
    lines = ["# Bank simulation record", "",
             "Six invented banks, three in the US and three in the EU, each commit one change a simulated day; the "
             "engine scans it and the bank then runs that day's business on its own COBOL programs. Every number "
             "here is counted from `ledger.jsonl` and `operations.jsonl` in this folder. Commentary on what the "
             "numbers mean is in `KNOWLEDGE.md`.", "",
             f"**Simulated through {max(r['date'] for r in rows)} (day {last}): {len(rows)} changes scanned, "
             f"{len(operations)} bank-days of business run.**" + (f" Updated {updated}." if updated else ""), "",
             "## How the engine is doing", ""]
    columns = [("All banks", rows)] + [(label, [r for r in rows if r["market"] == m]) for m, label in MARKETS]
    found = {label: measures(group) for label, group in columns}
    lines += table(["Measure"] + [label for label, _ in columns],
                   [[name] + [found[label][name] for label, _ in columns] for name in found["All banks"]])
    lines += ["", "## By program", ""]
    programs = sorted({program(r) for r in rows})
    lines += table(["Program", "Changes", "Defects caught", "Refactors proven", "Missed", "False alarms"], [
        [p, str(len(group := [r for r in rows if program(r) == p])),
         share(sum(r["outcome"] == "caught" for r in group), sum(r["kind"] == "defect" for r in group)),
         share(sum(r["outcome"] == "proven" for r in group), sum(r["kind"] == "refactor" for r in group)),
         str(sum(r["outcome"] == "missed" for r in group)), str(sum(r["outcome"] == "false-alarm" for r in group))]
        for p in programs])
    if operations:
        latest = max(o["day"] for o in operations)
        today = [o for o in operations if o["day"] == latest]
        lines += ["", f"## Each bank's business on {today[0]['date']}", ""]
        lines += table(["Bank", "Market", "Deposits", "Overdrawn", "Interest", "Posted / rejected",
                        "Payments approved / declined / reported", "Last month-end fees"], [
            [o["bank"], o["market"], amount(o["deposits"]), str(o["overdrawn"]), amount(o["interest"]),
             f"{o['posted']} / {o['rejected']}",
             f"{o['decisions'].get('APPROVE', 0)} / {o['decisions'].get('DECLINE', 0)} / {o['reported']}",
             next((amount(p["fees"]) for p in reversed(operations) if p["bank"] == o["bank"] and p["fees"]), "-")]
            for o in sorted(today, key=lambda o: o["bank"])])
    lines += ["", "## By simulated month", ""]
    months = sorted({r["date"][:7] for r in rows})
    lines += table(["Month", "Changes", "Defects caught", "Missed", "False alarms", "Interest paid", "Fees charged",
                    "Postings rejected"], [
        [m, str(len(group := [r for r in rows if r["date"].startswith(m)])),
         share(sum(r["outcome"] == "caught" for r in group), sum(r["kind"] == "defect" for r in group)),
         str(sum(r["outcome"] == "missed" for r in group)), str(sum(r["outcome"] == "false-alarm" for r in group)),
         amount(sum((Decimal(o["interest"]) for o in operations if o["date"].startswith(m)), Decimal(0))),
         amount(sum((Decimal(o["fees"]) for o in operations if o["date"].startswith(m) and o["fees"]), Decimal(0))),
         str(sum(o["rejected"] for o in operations if o["date"].startswith(m)))]
        for m in months])
    wrong = [r for r in rows if r["outcome"] in ("missed", "false-alarm", "inconclusive")][-RECENT:]
    lines += ["", "## Latest misses and false alarms", ""]
    lines += table(["Date", "Bank", "Change", "Where", "Engine said", "Truth", "Live traffic showed it"], [
        [r["date"], r["bank"], r["change"], f"`{r['provenance']['file']}:{r['provenance']['line']}`",
         r["engine"]["verdict"], f"{r['kind']} ({r['truth']['behaviour']} behaviour)",
         ("yes" if r["traffic"]["different"] else "no" if r["traffic"]["runs"] else "no traffic that day")
         if "traffic" in r else "not recorded"]
        for r in reversed(wrong)]) if wrong else ["None yet."]
    return "\n".join(lines) + "\n"
