"""One simulated bank that also runs public mainframe code: IBM's Cash Account service (ADR 017).

The four programs every simulated bank runs are tidy COBOL 85 with no CICS, Db2 or VSAM. Prairie
Ledger also carries IBM's Apache-2.0 Cash Account (corpus/ibm-cash-account), copied byte for byte,
plus a CICS resource definition for it that the simulation writes. Changes to that code come
from a catalogue with known truth, as in ADR 014, so the engine is scored on real mainframe code.

The engine cannot run CICS or Db2 programs yet, so behaviour on this code is always
inconclusive; what these changes test is impact analysis and the approval checks.
"""

import random
import shutil
import time
from dataclasses import dataclass
from pathlib import Path

from changeproof.banksim.banks import BANKS, Bank
from changeproof.banksim.estate import BEHAVIOUR, Change, render
from changeproof.banksim.run import GOVERNANCE, commit, git, governance_outcome, message, named, outcome
from changeproof.change import change_record
from changeproof.config import load_config
from changeproof.equivalence import equivalence

CORPUS = Path(__file__).resolve().parents[3] / "corpus" / "ibm-cash-account"  # RENAME: PINNED UPSTREAM COPY
HOST = next(b for b in BANKS if b.id == "prairie-ledger")  # RENAME: THE BANK THAT RUNS THE CASH ACCOUNT
COPYBOOKS = ["cash/copy"]  # RENAME: COPYBOOK FOLDERS OF THE GRAFTED CODE
LAYOUT = {  # RENAME: UPSTREAM PATH TO WHERE THE BANK KEEPS IT
    "COBOL/CASH00.cbl": "cash/src/CASH00.cbl",
    "COBOL/DCLCASH.cpy": "cash/copy/DCLCASH.cpy",
    "COBOL/DCLFRANK.cpy": "cash/copy/DCLFRANK.cpy",
    "DB2-DDL/DB2DDL.jcl": "cash/jcl/DB2DDL.jcl",
    "DB2-DDL/DB2BIND.jcl": "cash/jcl/DB2BIND.jcl",
    "VSAM/DEFKSDS.jcl": "cash/jcl/DEFKSDS.jcl",
}
# Written by the simulation, not upstream: the program, its transaction and the history file's dataset
# (DSNAME as defined in corpus/ibm-cash-account/VSAM/DEFKSDS.jcl:9). The transaction ID is made up.
CSD = """ DEFINE PROGRAM(CASH00) GROUP(CASHACCT)
 DEFINE TRANSACTION(CSH0) GROUP(CASHACCT)
        PROGRAM(CASH00)
 DEFINE FILE(HISTORY) GROUP(CASHACCT)
        DSNAME(SYSD.STOCK.HISTORY)
"""
COMPONENT = """  - id: cash-account
    path: cash
    language: cobol
    criticality: high
    data_stores: [STOCKTRD.CASHACCOUNTY, STOCKTRD.FRANKFURT1, SYSD.STOCK.HISTORY]
"""


@dataclass(frozen=True)
class CashChange(Change):
    reaches: frozenset[str] = frozenset()  # graph IDs a sound impact analysis must report


# PURPOSE: WRITES THE BANK'S OWN ESTATE, THEN THE CASH ACCOUNT, ITS CICS DEFINITION AND ITS CONFIG COMPONENT
def graft(bank: Bank, root: Path) -> None:
    render(bank, root)
    for upstream, here in LAYOUT.items():
        (root / here).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(CORPUS / upstream, root / here)
    (root / "cash" / "csd").mkdir(exist_ok=True)
    (root / "cash" / "csd" / "CASHACCT.csd").write_text(CSD, encoding="utf-8")
    config = (root / "changeproof.yaml").read_text(encoding="utf-8")
    (root / "changeproof.yaml").write_text(config.replace("\ncrypto:", f"\n{COMPONENT}crypto:", 1), encoding="utf-8")


# PURPOSE: EVERY CHANGE A DEVELOPER MAY MAKE TO THE CASH ACCOUNT, WITH WHAT IT REALLY DOES AND MUST REACH
def catalogue() -> list[CashChange]:
    cash, ddl, ksds, dclcash = (LAYOUT[k] for k in (
        "COBOL/CASH00.cbl", "DB2-DDL/DB2DDL.jcl", "VSAM/DEFKSDS.jcl", "COBOL/DCLCASH.cpy"))
    program, accounts = "program:CASH00", "table:STOCKTRD.CASHACCOUNTY"
    history = "cics-file:HISTORY"
    return [
        # WS-MSG is set but never displayed, returned or written, so its wording changes nothing.
        CashChange("cash-msg-wording", cash, "refactor", "Shorten the query success message",
                   "MOVE 'ACCOUNT QUERY SUCCESSFUL' TO WS-MSG", "MOVE 'ACCOUNT FOUND' TO WS-MSG",
                   frozenset({program})),
        CashChange("cash-name-case", cash, "refactor", "Spell the debit rate field in capitals",
                   "BALANCE - (RATES * BALANC-rate)", "BALANCE - (RATES * BALANC-RATE)"),
        CashChange("cash-credit-sign", cash, "defect", "Tidy the credit computation",
                   "BALANCE + (RATES", "BALANCE - (RATES", frozenset({program, accounts})),
        CashChange("cash-history-key", cash, "defect", "Simplify the history key",
                   "MOVE WS-TIME       TO WS-VK-TIME", "MOVE WS-DATE       TO WS-VK-TIME",
                   frozenset({program, history})),
        CashChange("cash-ksds-key", ksds, "defect", "Line the history key up with the record",
                   "KEYS(29 0)", "KEYS(30 0)", frozenset({"dataset:SYSD.STOCK.HISTORY", history, program})),
        CashChange("cash-balance-widen", dclcash, "intended", "Widen the cash balance host variable",
                   "BALANCE              PIC S9(7)V9(2)", "BALANCE              PIC S9(9)V9(2)",
                   frozenset({program})),
        CashChange("cash-ddl-widen", ddl, "intended", "Widen the cash balance column",
                   "balance      NUMERIC(9,2)", "balance      NUMERIC(11,2)", frozenset({program, accounts})),
    ]


# PURPOSE: THE HOST BANK'S REPOSITORY WITH THE CASH ACCOUNT, CREATED WITH ITS IMPORT COMMIT ON FIRST USE
def repository(state: Path) -> Path:
    root = state / "public" / HOST.id
    if not (root / ".git").is_dir():
        root.mkdir(parents=True)
        git(root, "init", "-q", "-b", "main")
        graft(HOST, root)
        commit(HOST, root, 0, HOST.developers[0],
               f"{HOST.ticket_project}-1: Import the {HOST.name} deposit programs and the Cash Account\n\n"
               f"Change-Request: CHG{BANKS.index(HOST) * 100000:07d}\nRequested-by: {named(HOST.requester)}\n"
               f"Approved-by: {named(HOST.approver)}\nChange-Type: normal")
    return root


# PURPOSE: WHETHER IMPACT REPORTED EVERYTHING THE CHANGE MUST REACH
def impact_outcome(expected: frozenset[str], predicate: dict) -> dict:
    seen = {c["id"] for c in predicate["changed"]} | {i["id"] for i in predicate["impacted"]}
    missing = sorted(expected - seen)
    if not expected:
        verdict = "nothing-required"
    elif not seen and not predicate["unresolved"]:
        verdict = "silent"
    else:
        verdict = "partial" if missing else "reached"
    return {"expected": sorted(expected), "missing": missing, "outcome": verdict}


# PURPOSE: ONE CASH ACCOUNT CHANGE COMMITTED, SCANNED AND SCORED; MAIN KEEPS IT ONLY ON EVIDENCE A REVIEWER WOULD ACCEPT
def scan(state: Path, day: int, runner=None, only: str | None = None) -> dict:
    started = time.monotonic()
    root = repository(state)
    rng = random.Random(f"{HOST.id}:cash:{day}")
    changes = catalogue()
    change = next(c for c in changes if c.id == only) if only else rng.choice(changes)
    governance = rng.choices(list(GOVERNANCE), weights=list(GOVERNANCE.values()))[0]
    developer = rng.choice(HOST.developers)
    path = root / change.path
    text = path.read_text(encoding="latin-1")
    line = text[:text.index(change.old)].count("\n") + 1
    path.write_text(text.replace(change.old, change.new, 1), encoding="latin-1")
    sha = commit(HOST, root, day, developer, message(HOST, day, change, governance, developer))
    kept = state / "baselines" / f"{HOST.id}-cash"  # RENAME: CHARACTERIZATION SUITES KEPT BETWEEN DAYS
    kept.mkdir(parents=True, exist_ok=True)
    run = equivalence(root, "HEAD", COPYBOOKS, scope="full-suite", runner=runner, baselines=kept)
    found = run.predicate
    record = change_record(root, sha, COPYBOOKS, config=load_config(root / "changeproof.yaml"), environ={})
    flags = record.gaps() + record.open_items()
    merged = found["verdict"] == "equivalent" or (
        change.kind == "intended" and governance == "governed" and found["verdict"] == "not-equivalent")
    if not merged:
        git(root, "update-ref", f"refs/rejected/day-{day}", sha)
        git(root, "reset", "-q", "--hard", "HEAD~1")
    expected_flag = governance != "governed"
    return {
        "day": day, "bank": HOST.id, "market": HOST.market, "change": change.id, "kind": change.kind,
        "summary": change.summary, "commit": sha, "provenance": {"file": change.path, "line": line},
        "truth": {"behaviour": BEHAVIOUR[change.kind], "governance": governance},
        "engine": {"verdict": found["verdict"], "tests": found["summary"]["total"],
                   "different": found["summary"]["different"],
                   "untested": [f"{u.get('program', u['provenance']['file'])}: {u['reason']}" for u in found["untested"]],
                   "changed": len(run.impact.predicate["changed"]), "impacted": len(run.impact.predicate["impacted"])},
        "outcome": outcome(change.kind, found["verdict"]),
        "impact": impact_outcome(change.reaches, run.impact.predicate),
        "governance": {"expected_flag": expected_flag, "open_items": flags,
                       "outcome": governance_outcome(expected_flag, bool(flags))},
        "merged": merged, "seconds": round(time.monotonic() - started),
    }
