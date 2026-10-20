"""One simulated business day: each bank's developers commit a change, the engine scans it, and the bank
runs its day's business on whatever main now holds.

The scan is the same one a bank would run: the change record (who, why, approvals) and the
behavioural-equivalence check over every program. Each result is scored against what the change
really does, kept in an append-only ledger, and the bank's main branch moves only when its
reviewers would accept the change on that evidence. The day's real traffic is also run through the
changed program before and after the change, to see whether live data would have shown what the
scan did or did not.
"""

import json
import random
import shutil
import subprocess
import tempfile
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from changeproof.banksim.banks import BANKS, Bank
from changeproof.banksim.estate import BEHAVIOUR, PROGRAMS, Change, catalogue, render
from changeproof.banksim.record import page
from changeproof.banksim.operations import load_book, run_rows, save_book, settle, traffic
from changeproof.change import change_record
from changeproof.change.git import checkout_tree
from changeproof.characterize import LocalRunner
from changeproof.config import load_config
from changeproof.equivalence import equivalence

FIRST_DAY = date(2026, 10, 20)  # RENAME: SIMULATED DATE OF THE IMPORT COMMIT
GOVERNANCE = {"governed": 7, "self-approved": 1, "no-ticket": 1, "emergency": 1}  # RENAME: HOW CHANGES ARE APPROVED, WITH WEIGHTS
LEDGER = "ledger.jsonl"
OPERATIONS = "operations.jsonl"
RECORD = "RECORD.md"  # RENAME: THE ONE-PAGE RECORD THE OWNER READS


# PURPOSE: RUNS GIT IN A BANK REPOSITORY WITH NO USER OR SYSTEM CONFIG
def git(root: Path, *args: str, env: dict | None = None) -> str:
    base = {"PATH": "/usr/bin:/bin", "HOME": str(root), "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_NOSYSTEM": "1"}
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True,
                          env=base | (env or {})).stdout.strip()


# PURPOSE: COMMITS THE WORK TREE AS A PERSON ON A SIMULATED DAY AT 09:30 BANK TIME
def commit(bank: Bank, root: Path, day: int, author: tuple[str, str], message: str) -> str:
    when = f"{FIRST_DAY + timedelta(days=day)}T09:30:00{bank.utc_offset}"
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message, env={
        "GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1], "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_NAME": author[0], "GIT_COMMITTER_EMAIL": author[1], "GIT_COMMITTER_DATE": when})
    return git(root, "rev-parse", "HEAD")


# PURPOSE: "NAME <EMAIL>" FOR A COMMIT TRAILER
def named(who: tuple[str, str]) -> str:
    return f"{who[0]} <{who[1]}>"


# PURPOSE: THE COMMIT MESSAGE A DEVELOPER WRITES FOR A CHANGE UNDER ONE GOVERNANCE PATH
def message(bank: Bank, day: int, change: Change, governance: str, developer: tuple[str, str]) -> str:
    if governance == "no-ticket":
        return change.summary
    number = BANKS.index(bank) * 100000 + day
    approver = developer if governance in ("self-approved", "emergency") else bank.approver
    kind = "emergency" if governance == "emergency" else "normal"
    return (f"{bank.ticket_project}-{day}: {change.summary}\n\n"
            f"Change-Request: CHG{number:07d}\nRequested-by: {named(bank.requester)}\n"
            f"Approved-by: {named(approver)}\nChange-Type: {kind}")


# PURPOSE: THE BANK'S REPOSITORY, CREATED WITH ITS IMPORT COMMIT ON FIRST USE
def repository(bank: Bank, state: Path) -> Path:
    root = state / "banks" / bank.id
    if not (root / ".git").is_dir():
        root.mkdir(parents=True)
        git(root, "init", "-q", "-b", "main")
        render(bank, root)
        commit(bank, root, 0, bank.developers[0],
               f"{bank.ticket_project}-1: Import the {bank.name} deposit programs\n\n"
               f"Change-Request: CHG{BANKS.index(bank) * 100000:07d}\nRequested-by: {named(bank.requester)}\n"
               f"Approved-by: {named(bank.approver)}\nChange-Type: normal")
    return root


# PURPOSE: WHAT THE SCAN GOT RIGHT OR WRONG ABOUT BEHAVIOUR, GIVEN WHAT THE CHANGE REALLY DOES
def outcome(kind: str, verdict: str) -> str:
    if verdict == "inconclusive":
        return "inconclusive"
    if BEHAVIOUR[kind] == "same":
        return "proven" if verdict == "equivalent" else "false-alarm"
    if verdict == "equivalent":
        return "missed"
    return "caught" if kind == "defect" else "confirmed"


# PURPOSE: WHAT THE SCAN GOT RIGHT OR WRONG ABOUT APPROVALS
def governance_outcome(expected: bool, flagged: bool) -> str:
    return {(True, True): "flagged", (False, False): "clean", (True, False): "missed",
            (False, True): "false-flag"}[expected, flagged]


# PURPOSE: ONE BANK'S CHANGE FOR THE DAY, SCANNED AND SCORED, THEN THE DAY'S BUSINESS RUN ON MAIN
def scan(bank: Bank, state: Path, day: int, runner=None, only: str | None = None) -> tuple[dict, dict]:
    started = time.monotonic()
    runner = runner or LocalRunner()
    root = repository(bank, state)
    rng = random.Random(f"{bank.id}:{day}")
    open_changes = [c for c in catalogue(bank) if (root / c.path).read_text(encoding="utf-8").count(c.old) == 1]
    change = next(c for c in open_changes if c.id == only) if only else rng.choice(open_changes)
    governance = rng.choices(list(GOVERNANCE), weights=list(GOVERNANCE.values()))[0]
    developer = rng.choice(bank.developers)
    path = root / change.path
    text = path.read_text(encoding="utf-8")
    line = text[:text.index(change.old)].count("\n") + 1
    path.write_text(text.replace(change.old, change.new, 1), encoding="utf-8")
    sha = commit(bank, root, day, developer, message(bank, day, change, governance, developer))
    kept = state / "baselines" / bank.id  # RENAME: CHARACTERIZATION SUITES KEPT BETWEEN DAYS
    kept.mkdir(parents=True, exist_ok=True)
    found = equivalence(root, "HEAD", scope="full-suite", runner=runner, baselines=kept).predicate
    record = change_record(root, sha, config=load_config(root / "changeproof.yaml"), environ={})
    flags = record.gaps() + record.open_items()
    merged = found["verdict"] == "equivalent" or (
        change.kind == "intended" and governance == "governed" and found["verdict"] == "not-equivalent")
    base = git(root, "rev-parse", "HEAD~1")
    if not merged:
        git(root, "update-ref", f"refs/rejected/day-{day}", sha)
        git(root, "reset", "-q", "--hard", base)
    on = FIRST_DAY + timedelta(days=day)
    book = load_book(bank, state)
    today = traffic(bank, book, day, on)
    changed = Path(change.path).stem
    with tempfile.TemporaryDirectory() as scratch:
        before, after = checkout_tree(root, base, Path(scratch) / "before"), checkout_tree(root, sha, Path(scratch) / "after")
        live, other = (after, before) if merged else (before, after)
        results = {p: run_rows(live, p, today[p], runner) for p in PROGRAMS}
        shadow = run_rows(other, changed, today[changed], runner)
    operations = {"day": day, "bank": bank.id, "market": bank.market} | settle(book, today, results, on)
    save_book(bank, state, book)
    expected_flag = governance != "governed"
    return {
        "day": day, "date": str(FIRST_DAY + timedelta(days=day)), "bank": bank.id, "name": bank.name,
        "region": bank.region, "market": bank.market, "change": change.id, "kind": change.kind,
        "summary": change.summary, "commit": sha, "provenance": {"file": change.path, "line": line},
        "truth": {"behaviour": BEHAVIOUR[change.kind], "governance": governance},
        "engine": {"verdict": found["verdict"], "tests": found["summary"]["total"],
                   "different": found["summary"]["different"], "error": found["summary"]["error"],
                   "differing_programs": sorted({t["target"]["name"] for t in found["tests"]
                                                 if t["result"] == "different"}),
                   "untested": [u["reason"] for u in found["untested"]]},
        "outcome": outcome(change.kind, found["verdict"]),
        "governance": {"expected_flag": expected_flag, "open_items": flags,
                       "outcome": governance_outcome(expected_flag, bool(flags))},
        "traffic": {"program": changed, "runs": len(shadow),
                    "different": sum(a != b for a, b in zip(results[changed], shadow))},
        "merged": merged, "seconds": round(time.monotonic() - started),
    }, operations


# PURPOSE: APPENDS ROWS TO ONE OF THE STATE'S JSON-LINES FILES
def append(state: Path, rows: list[dict], name: str = LEDGER) -> None:
    with (state / name).open("a", encoding="utf-8") as out:
        out.writelines(json.dumps(row, sort_keys=True) + "\n" for row in rows)


# PURPOSE: SCANS ONE BANK'S CHANGE FOR THE DAY, RUNS ITS BUSINESS AND LEDGERS BOTH
def tick(bank: Bank, state: Path, day: int, runner=None, only: str | None = None) -> dict:
    row, operations = scan(bank, state, day, runner, only)
    append(state, [row])
    append(state, [operations], OPERATIONS)
    return row


# PURPOSE: ONE SIMULATED DAY ACROSS EVERY BANK, BANKS RUN SIDE BY SIDE
def business_day(state: Path, day: int, workers: int) -> list[dict]:
    with ProcessPoolExecutor(workers) as pool:
        found = list(pool.map(scan, BANKS, [state] * len(BANKS), [day] * len(BANKS)))
    append(state, [row for row, _ in found])
    append(state, [operations for _, operations in found], OPERATIONS)
    return [row for row, _ in found]


# PURPOSE: THE ROWS OF ONE OF THE STATE'S JSON-LINES FILES, OLDEST FIRST
def ledger(state: Path, name: str = LEDGER) -> list[dict]:
    path = state / name
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()] if path.exists() else []


# PURPOSE: TOTALS OVER LEDGER ROWS: OUTCOMES OVERALL, BY MARKET, BY BANK AND BY CHANGE, PLUS RUN TIME
def scorecard(rows: list[dict]) -> dict:
    # PURPOSE: OUTCOME AND GOVERNANCE COUNTS FOR A GROUP OF ROWS
    def totals(group: list[dict]) -> dict:
        return {"changes": len(group), "by_outcome": dict(Counter(r["outcome"] for r in group)),
                "governance": dict(Counter(r["governance"]["outcome"] for r in group))}

    # PURPOSE: ROWS GROUPED BY ONE FIELD
    def grouped(key: str) -> dict:
        found: dict[str, list[dict]] = {}
        for row in rows:
            found.setdefault(row[key], []).append(row)
        return {k: totals(v) for k, v in sorted(found.items())}

    return totals(rows) | {"days": len({r["day"] for r in rows}), "by_market": grouped("market"),
                           "by_bank": grouped("bank"), "by_change": grouped("change"),
                           "seconds": sum(r["seconds"] for r in rows)}


# PURPOSE: COPIES THE LEDGERS, BOOKS, SCORECARD, ONE-PAGE RECORD AND EACH BANK'S HISTORY (AS A GIT BUNDLE) TO A KEEPING FOLDER
def save(state: Path, keep: Path) -> None:
    for folder in ("banks", "accounts"):
        (keep / folder).mkdir(parents=True, exist_ok=True)
    rows, operations = ledger(state), ledger(state, OPERATIONS)
    for name in (LEDGER, OPERATIONS):
        if (state / name).exists():
            shutil.copyfile(state / name, keep / name)
    for book in sorted((state / "accounts").glob("*.json")) if (state / "accounts").is_dir() else []:
        shutil.copyfile(book, keep / "accounts" / book.name)
    (keep / "scorecard.json").write_text(json.dumps(scorecard(rows), indent=1) + "\n", encoding="utf-8")
    updated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")  # RENAME: WHEN THE PAGE WAS LAST WRITTEN
    (keep / RECORD).write_text(page(rows, operations, updated), encoding="utf-8")
    for bank in BANKS:
        if (root := state / "banks" / bank.id).is_dir():
            git(root, "bundle", "create", "-q", str((keep / "banks" / f"{bank.id}.bundle").resolve()), "--all")


# PURPOSE: REBUILDS A WORKING STATE FROM A KEEPING FOLDER, SO A FRESH MACHINE CARRIES ON WHERE THE LAST LEFT OFF
def restore(state: Path, keep: Path) -> None:
    (state / "accounts").mkdir(parents=True, exist_ok=True)
    for name in (LEDGER, OPERATIONS):
        if (keep / name).exists():
            shutil.copyfile(keep / name, state / name)
    for book in sorted((keep / "accounts").glob("*.json")) if (keep / "accounts").is_dir() else []:
        shutil.copyfile(book, state / "accounts" / book.name)
    for bundle in sorted((keep / "banks").glob("*.bundle")) if (keep / "banks").is_dir() else []:
        root = state / "banks" / bundle.stem
        if not root.exists():
            root.parent.mkdir(parents=True, exist_ok=True)
            git(root.parent, "clone", "-q", "--mirror", str(bundle.resolve()), str(root / ".git"))
            git(root, "config", "--bool", "core.bare", "false")
            git(root, "reset", "-q", "--hard", "main")
