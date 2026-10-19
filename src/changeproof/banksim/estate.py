"""A bank's source tree and the catalogue of changes its developers make to it.

Each catalogued change says what it really does (its ground truth) so the scan can be scored:
a refactor keeps behaviour, a defect breaks it, an intended change alters it on purpose.
"""

from dataclasses import dataclass
from decimal import Decimal
from importlib.resources import files
from pathlib import Path

from changeproof.banksim.banks import Bank
from changeproof.markets import MARKETS

PROGRAMS = ("INTACCR", "FEEASSES", "PAYSCRN", "POSTTXN")  # RENAME: PROGRAMS EVERY BANK RUNS
BEHAVIOUR = {"refactor": "same", "defect": "different", "intended": "different"}  # RENAME: CHANGE KIND TO TRUE BEHAVIOUR


@dataclass(frozen=True)
class Change:
    id: str
    path: str
    kind: str  # refactor, defect or intended
    summary: str
    old: str
    new: str


CONFIG = """version: 0.1
market: {market}
system:
  name: {id}-core
  owner: {owner}
  classification: confidential
components:
  - id: deposits-core
    path: src
    language: cobol
    criticality: high
    data_stores: [ACCOUNTS]
crypto:
  profile: hybrid
  signing: [ml-dsa-87, ecdsa-p384]
  release_signing: lms-sha256-192
  hash: sha-384
frameworks: {frameworks}
"""


# PURPOSE: THE BANK'S RULE VALUES PLUS ITS NAME AND CURRENCY, AS THE TEMPLATES NAME THEM
def values(bank: Bank) -> dict[str, str]:
    return bank.rules | {"bank": bank.name, "currency": bank.currency}


# PURPOSE: WRITES THE BANK'S PROGRAMS AND CHANGEPROOF.YAML INTO A FOLDER
def render(bank: Bank, root: Path) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    for name in PROGRAMS:
        template = files("changeproof.banksim").joinpath("estate", f"{name}.cbl").read_text(encoding="utf-8")
        (root / "src" / f"{name}.cbl").write_text(template.format(**values(bank)), encoding="utf-8")
    (root / "changeproof.yaml").write_text(CONFIG.format(
        market=bank.market, id=bank.id, owner=bank.approver[0],
        frameworks="[" + ", ".join(MARKETS[bank.market].frameworks) + "]"), encoding="utf-8")


# PURPOSE: A MONEY OR RATE LITERAL WITH THE SAME NUMBER OF DECIMALS AS THE ONE IT REPLACES
def literal(value: Decimal, like: str) -> str:
    return f"{value:.{len(like.split('.')[1])}f}"


# PURPOSE: EVERY CHANGE A DEVELOPER AT THIS BANK MAY MAKE, WITH WHAT IT REALLY DOES
def catalogue(bank: Bank) -> list[Change]:
    r = bank.rules
    other_basis = "360" if r["basis"] == "365" else "365"
    raised_rate = literal(Decimal(r["rate_high"]) + Decimal("0.0025"), r["rate_high"])
    raised_fee = literal(Decimal(r["retail_fee"]) + 2, r["retail_fee"])
    raised_limit = literal(Decimal(r["online_limit"]) * 2, r["online_limit"])
    lower_od_fee = literal(Decimal(r["overdraft_fee"]) - Decimal("2.50"), r["overdraft_fee"])
    slipped_per_txn = literal(Decimal(r["per_txn"]) * 10, r["per_txn"])
    i, f, p, t = (f"src/{n}.cbl" for n in PROGRAMS)
    return [
        Change("intaccr-init", i, "refactor", "Initialise the interest field with INITIALIZE",
               "MOVE 0 TO LK-INTEREST", "INITIALIZE LK-INTEREST"),
        Change("intaccr-not-positive", i, "refactor", "State the no-accrual test as NOT positive",
               "IF LK-BALANCE <= 0", "IF NOT LK-BALANCE > 0"),
        Change("intaccr-tier-strict", i, "defect", "Tidy the savings tier test",
               f"IF LK-BALANCE >= {r['tier']}", f"IF LK-BALANCE > {r['tier']}"),
        Change("intaccr-truncate", i, "defect", "Simplify the interest calculation",
               "COMPUTE LK-INTEREST ROUNDED =", "COMPUTE LK-INTEREST ="),
        Change("intaccr-basis", i, "defect", "Align the accrual day count with the general ledger",
               f"/ {r['basis']}", f"/ {other_basis}"),
        Change("intaccr-rate-up", i, "intended", f"Raise the top savings rate to {raised_rate}",
               f"MOVE {r['rate_high']} TO WS-RATE", f"MOVE {raised_rate} TO WS-RATE"),
        Change("fee-compute", f, "refactor", "Write the retail fee as a COMPUTE",
               f"MOVE {r['retail_fee']} TO LK-FEE", f"COMPUTE LK-FEE = {r['retail_fee']}"),
        Change("fee-free-txns-inclusive", f, "refactor", "Count free transactions inclusively",
               f"IF LK-TXN-COUNT > {r['free_txns']}", f"IF LK-TXN-COUNT >= {r['free_txns']}"),
        Change("fee-waiver-strict", f, "defect", "Tidy the retail waiver test",
               f"IF LK-AVG-BALANCE >= {r['retail_minimum']}", f"IF LK-AVG-BALANCE > {r['retail_minimum']}"),
        Change("fee-per-txn-slip", f, "defect", "Update the per-transaction charge",
               f"* {r['per_txn']}", f"* {slipped_per_txn}"),
        Change("fee-retail-up", f, "intended", f"Raise the retail monthly fee to {raised_fee}",
               f"MOVE {r['retail_fee']} TO LK-FEE", f"MOVE {raised_fee} TO LK-FEE"),
        Change("paysc-swap-compare", p, "refactor", "Write the limit test from the limit's side",
               "IF WS-TOTAL > WS-LIMIT", "IF WS-LIMIT < WS-TOTAL"),
        Change("paysc-report-strict", p, "defect", "Tidy the reporting threshold test",
               f"IF LK-AMOUNT >= {r['report_threshold']}", f"IF LK-AMOUNT > {r['report_threshold']}"),
        Change("paysc-daily-ignored", p, "defect", "Simplify the daily total",
               "COMPUTE WS-TOTAL = LK-DAILY-USED + LK-AMOUNT", "COMPUTE WS-TOTAL = LK-AMOUNT"),
        Change("paysc-online-up", p, "intended", f"Raise the online daily limit to {raised_limit}",
               f"MOVE {r['online_limit']} TO WS-LIMIT", f"MOVE {raised_limit} TO WS-LIMIT"),
        Change("post-compute", t, "refactor", "Write the credit posting as a COMPUTE",
               "ADD TRAN-AMOUNT TO ACCT-BALANCE",
               "COMPUTE ACCT-BALANCE = ACCT-BALANCE + TRAN-AMOUNT"),
        Change("post-credit-reversed", t, "defect", "Use one statement for both postings",
               "ADD TRAN-AMOUNT TO ACCT-BALANCE", "SUBTRACT TRAN-AMOUNT FROM ACCT-BALANCE"),
        Change("post-limit-ignored", t, "defect", "Simplify the overdraft test",
               "< 0 - ACCT-LIMIT", "< 0"),
        Change("post-rc-dropped", t, "defect", "Stop failing the job on rejects",
               "MOVE 4 TO RETURN-CODE", "MOVE 0 TO RETURN-CODE"),
        Change("post-od-fee-down", t, "intended", f"Lower the overdraft fee to {lower_od_fee}",
               f"SUBTRACT {r['overdraft_fee']} FROM ACCT-BALANCE", f"SUBTRACT {lower_od_fee} FROM ACCT-BALANCE"),
    ]
