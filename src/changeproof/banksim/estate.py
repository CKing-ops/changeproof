"""A bank's source tree and the catalogue of changes its developers make to it.

Each catalogued change says what it really does (its ground truth) so the scan can be scored:
a refactor keeps behaviour, a defect breaks it, an intended change alters it on purpose.
"""

import re
from dataclasses import dataclass
from decimal import Decimal
from importlib.resources import files
from itertools import pairwise
from pathlib import Path

from changeproof.banksim.banks import Bank
from changeproof.markets import MARKETS

PROGRAMS = ("INTACCR", "FEEASSES", "PAYSCRN", "POSTTXN",  # RENAME: PROGRAMS EVERY BANK RUNS
            "LOANPMT", "FXCONV", "CASHAGG")
BEHAVIOUR = {"refactor": "same", "defect": "different", "intended": "different"}  # RENAME: CHANGE KIND TO TRUE BEHAVIOUR


@dataclass(frozen=True)
class Change:
    id: str
    path: str
    kind: str  # refactor, defect or intended
    summary: str
    old: str
    new: str
    count: int = 1  # occurrences of old the change replaces, all of them


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


# PURPOSE: A PROGRAM'S TEMPLATE TEXT
def template(name: str) -> str:
    return files("changeproof.banksim").joinpath("estate", f"{name}.cbl").read_text(encoding="utf-8")


# PURPOSE: WRITES ONE OF THE BANK'S PROGRAMS INTO A SOURCE TREE
def render_program(bank: Bank, root: Path, name: str) -> None:
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / f"{name}.cbl").write_text(template(name).format(**values(bank)), encoding="utf-8")


# PURPOSE: WRITES THE BANK'S PROGRAMS AND CHANGEPROOF.YAML INTO A FOLDER
def render(bank: Bank, root: Path) -> None:
    for name in PROGRAMS:
        render_program(bank, root, name)
    (root / "changeproof.yaml").write_text(CONFIG.format(
        market=bank.market, id=bank.id, owner=bank.approver[0],
        frameworks="[" + ", ".join(MARKETS[bank.market].frameworks) + "]"), encoding="utf-8")


# PURPOSE: A MONEY OR RATE LITERAL WITH THE SAME NUMBER OF DECIMALS AS THE ONE IT REPLACES
def literal(value: Decimal, like: str) -> str:
    return f"{value:.{len(like.split('.')[1])}f}"


# PURPOSE: THE BANK'S RULE VALUES AS ITS SOURCE TREE HOLDS THEM NOW, AFTER THE INTENDED CHANGES MERGED SO FAR
def current(bank: Bank, root: Path) -> dict[str, str]:
    rules = dict(bank.rules)
    for name in PROGRAMS:
        path = root / "src" / f"{name}.cbl"
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        lines = template(name).splitlines()
        cursor = 0  # windows are found in template order, so a repeated statement is not read off its twin
        for before, line in pairwise(lines):
            window = f"{before}\n{line}"
            keys = re.findall(r"\{(\w+)\}", window)
            if "{" not in line or not set(keys) <= rules.keys():
                continue
            pattern = re.sub(r"\\\{\w+\\\}", lambda _: r"(\S+)", re.escape(window))
            if found := re.compile(f"^{pattern}$", re.MULTILINE).search(text, cursor):
                rules.update(zip(keys, found.groups()))
                cursor = text.index("\n", found.start()) + 1
    return rules


# PURPOSE: EVERY CHANGE A DEVELOPER AT THIS BANK MAY MAKE TO THE GIVEN RULE VALUES, WITH WHAT IT REALLY DOES
def catalogue(bank: Bank, rules: dict[str, str] | None = None) -> list[Change]:
    r = rules or bank.rules
    other_basis = "360" if r["basis"] == "365" else "365"
    raised_rate = shifted(r, "rate_high", "0.0025")
    lower_rate = shifted(r, "rate_high", "-0.0025")
    raised_fee = shifted(r, "retail_fee", "2")
    lower_fee = shifted(r, "retail_fee", "-2")
    raised_limit = literal(Decimal(r["online_limit"]) * 2, r["online_limit"])
    lower_limit = literal(Decimal(r["online_limit"]) / 2, r["online_limit"])
    lower_od_fee = shifted(r, "overdraft_fee", "-2.50")
    raised_od_fee = shifted(r, "overdraft_fee", "2.50")
    slipped_per_txn = literal(Decimal(r["per_txn"]) * 10, r["per_txn"])
    i, f, p, t, loan, fx, cash = (f"src/{n}.cbl" for n in PROGRAMS)
    changes = [
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
        Change("intaccr-rate-down", i, "intended", f"Lower the top savings rate to {lower_rate}",
               f"MOVE {r['rate_high']} TO WS-RATE", f"MOVE {lower_rate} TO WS-RATE"),
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
        Change("fee-retail-down", f, "intended", f"Lower the retail monthly fee to {lower_fee}",
               f"MOVE {r['retail_fee']} TO LK-FEE", f"MOVE {lower_fee} TO LK-FEE"),
        Change("paysc-swap-compare", p, "refactor", "Write the limit test from the limit's side",
               "IF WS-TOTAL > WS-LIMIT", "IF WS-LIMIT < WS-TOTAL"),
        Change("paysc-report-strict", p, "defect", "Tidy the reporting threshold test",
               f"IF LK-AMOUNT >= {r['report_threshold']}", f"IF LK-AMOUNT > {r['report_threshold']}"),
        Change("paysc-daily-ignored", p, "defect", "Simplify the daily total",
               "COMPUTE WS-TOTAL = LK-DAILY-USED + LK-AMOUNT", "COMPUTE WS-TOTAL = LK-AMOUNT"),
        Change("paysc-online-up", p, "intended", f"Raise the online daily limit to {raised_limit}",
               f"MOVE {r['online_limit']} TO WS-LIMIT", f"MOVE {raised_limit} TO WS-LIMIT"),
        Change("paysc-online-down", p, "intended", f"Lower the online daily limit to {lower_limit}",
               f"MOVE {r['online_limit']} TO WS-LIMIT", f"MOVE {lower_limit} TO WS-LIMIT"),
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
        Change("post-od-fee-up", t, "intended", f"Raise the overdraft fee to {raised_od_fee}",
               f"SUBTRACT {r['overdraft_fee']} FROM ACCT-BALANCE", f"SUBTRACT {raised_od_fee} FROM ACCT-BALANCE"),
    ]
    changes += loan_changes(r, loan) + fx_changes(r, fx) + cash_changes(r, cash, bank.rules["cash_op"])
    return changes + [back(c) for c in changes if c.kind == "refactor"]


# PURPOSE: A RULE VALUE MOVED BY A STEP, IN THE RULE'S OWN NUMBER OF DECIMALS
def shifted(r: dict[str, str], rule: str, step: str) -> str:
    return literal(Decimal(r[rule]) + Decimal(step), r[rule])


# PURPOSE: THE SAME REFACTOR WRITTEN BACK THE OTHER WAY, SO REFACTORS KEEP COMING AFTER ONE MERGES
def back(change: Change) -> Change:
    return Change(f"{change.id}-back", change.path, "refactor", f"Undo: {change.summary}", change.new, change.old,
                  change.count)


B = "\n" + " " * 15  # RENAME: LINE BREAK INTO A STATEMENT INSIDE AN IF
BB = "\n" + " " * 19  # RENAME: LINE BREAK INTO A STATEMENT TWO LEVELS DOWN


# PURPOSE: LOAN INSTALLMENT CHANGES: ROUNDING, CLAMPS, DAY-COUNT BOUNDARIES, A DATA-DIVISION PRECISION SLIP
def loan_changes(r: dict[str, str], path: str) -> list[Change]:
    grace = int(r["grace_days"])
    floor = f"IF LK-LATE-FEE < {r['late_min']}{BB}MOVE {r['late_min']} TO LK-LATE-FEE{B}END-IF"
    cap = f"IF LK-LATE-FEE > {r['late_cap']}{BB}MOVE {r['late_cap']} TO LK-LATE-FEE{B}END-IF"
    changes = [
        Change("loan-subtract-giving", path, "refactor", "Write the principal portion as a SUBTRACT",
               "COMPUTE LK-TO-PRINCIPAL = LK-PAYMENT - LK-INTEREST",
               f"SUBTRACT LK-INTEREST FROM LK-PAYMENT{B}    GIVING LK-TO-PRINCIPAL"),
        Change("loan-grace-inclusive", path, "refactor", "State the grace period inclusively",
               f"IF LK-DAYS-LATE > {grace}", f"IF LK-DAYS-LATE >= {grace + 1}"),
        Change("loan-clamp-order", path, "refactor", "Apply the late fee cap before the floor",
               f"{floor}{B}{cap}", f"{cap}{B}{floor}"),
        Change("loan-interest-truncate", path, "defect", "Simplify the loan interest calculation",
               "COMPUTE LK-INTEREST ROUNDED =", "COMPUTE LK-INTEREST ="),
        Change("loan-late-fee-truncate", path, "defect", "Simplify the late fee calculation",
               "COMPUTE LK-LATE-FEE ROUNDED =", "COMPUTE LK-LATE-FEE ="),
        Change("loan-delinquent-strict", path, "defect", "Tidy the delinquency test",
               f"IF LK-DAYS-LATE >= {r['delinquent_days']}", f"IF LK-DAYS-LATE > {r['delinquent_days']}"),
        Change("loan-rate-mixup", path, "defect", "Reorder the loan rate table",
               f"MOVE {r['apr_auto']} TO WS-APR", f"MOVE {r['apr_personal']} TO WS-APR"),
        Change("loan-late-cap-down", path, "intended", f"Lower the late fee cap to {shifted(r, 'late_cap', '-5')}",
               cap, cap.replace(r["late_cap"], shifted(r, "late_cap", "-5"))),
        Change("loan-late-cap-up", path, "intended", f"Raise the late fee cap to {shifted(r, 'late_cap', '5')}",
               cap, cap.replace(r["late_cap"], shifted(r, "late_cap", "5"))),
        Change("loan-grace-up", path, "intended", f"Extend the grace period to {grace + 5} days",
               f"IF LK-DAYS-LATE > {grace}", f"IF LK-DAYS-LATE > {grace + 5}"),
        Change("loan-mortgage-rate-up", path, "intended",
               f"Raise the mortgage rate to {shifted(r, 'apr_mortgage', '0.00125')}",
               f"MOVE {r['apr_mortgage']} TO WS-APR", f"MOVE {shifted(r, 'apr_mortgage', '0.00125')} TO WS-APR"),
        Change("loan-mortgage-rate-down", path, "intended",
               f"Lower the mortgage rate to {shifted(r, 'apr_mortgage', '-0.00125')}",
               f"MOVE {r['apr_mortgage']} TO WS-APR", f"MOVE {shifted(r, 'apr_mortgage', '-0.00125')} TO WS-APR"),
    ]
    if grace > 5:
        changes.append(Change("loan-grace-down", path, "intended", f"Shorten the grace period to {grace - 5} days",
                              f"IF LK-DAYS-LATE > {grace}", f"IF LK-DAYS-LATE > {grace - 5}"))
    if any(Decimal(r[k]) != Decimal(r[k]).quantize(Decimal("0.0001")) for k in ("apr_mortgage", "apr_auto", "apr_personal")):
        changes.append(Change("loan-apr-precision", path, "defect", "Shorten the loan rate field",
                              "WS-APR                  PIC 9V9(6)", "WS-APR                  PIC 9V9(4)"))
    return [c for c in changes if Decimal(r["late_min"]) <= Decimal(cap_of(c, r))]


# PURPOSE: THE LATE FEE CAP A CHANGE LEAVES IN PLACE, SO NO CHANGE PUTS THE CAP BELOW THE FLOOR
def cap_of(change: Change, r: dict[str, str]) -> str:
    found = re.search(r"IF LK-LATE-FEE > (\S+)", change.new)
    return found.group(1) if found else r["late_cap"]


# PURPOSE: FOREIGN EXCHANGE CHANGES: ROUNDING, A SWAPPED RATE TABLE, A FEE ON THE WRONG AMOUNT
def fx_changes(r: dict[str, str], path: str) -> list[Change]:
    one = f"MOVE {r['fx1_rate']} TO WS-RATE{B}WHEN '{r['fx2']}'{BB}MOVE {r['fx2_rate']} TO WS-RATE"
    swapped = f"MOVE {r['fx2_rate']} TO WS-RATE{B}WHEN '{r['fx2']}'{BB}MOVE {r['fx1_rate']} TO WS-RATE"
    changes = [
        Change("fx-multiply", path, "refactor", "Write the conversion as a MULTIPLY",
               "COMPUTE LK-CONVERTED ROUNDED = LK-AMOUNT * WS-RATE",
               f"MULTIPLY LK-AMOUNT BY WS-RATE{B}GIVING LK-CONVERTED ROUNDED"),
        Change("fx-convert-truncate", path, "defect", "Simplify the conversion",
               "COMPUTE LK-CONVERTED ROUNDED =", "COMPUTE LK-CONVERTED ="),
        Change("fx-rate-swap", path, "defect", f"Reorder the {r['fx1']} and {r['fx2']} rates", one, swapped),
        Change("fx-premier-inverted", path, "defect", "Tidy the premier customer test",
               "IF NOT CUST-PREMIER", "IF CUST-PREMIER"),
        Change("fx-fee-on-amount", path, "defect", "Charge the spread on the instructed amount",
               f"LK-CONVERTED * {r['fx_spread']}", f"LK-AMOUNT * {r['fx_spread']}"),
        Change("fx-review-strict", path, "defect", "Tidy the review threshold test",
               f"IF LK-CONVERTED >= {r['fx_review']}", f"IF LK-CONVERTED > {r['fx_review']}"),
        Change("fx-review-up", path, "intended", f"Raise the review threshold to {shifted(r, 'fx_review', r['fx_review'])}",
               f"IF LK-CONVERTED >= {r['fx_review']}",
               f"IF LK-CONVERTED >= {shifted(r, 'fx_review', r['fx_review'])}"),
        Change("fx-min-fee-up", path, "intended", f"Raise the minimum FX fee to {shifted(r, 'fx_min_fee', '1')}",
               f"IF LK-FX-FEE < {r['fx_min_fee']}{BB}MOVE {r['fx_min_fee']} TO LK-FX-FEE",
               f"IF LK-FX-FEE < {shifted(r, 'fx_min_fee', '1')}{BB}MOVE {shifted(r, 'fx_min_fee', '1')} TO LK-FX-FEE"),
        Change("fx-spread-up", path, "intended", f"Widen the FX spread to {shifted(r, 'fx_spread', '0.0010')}",
               f"LK-CONVERTED * {r['fx_spread']}", f"LK-CONVERTED * {shifted(r, 'fx_spread', '0.0010')}"),
    ]
    if Decimal(r["fx_spread"]) > Decimal("0.0020"):
        changes.append(Change("fx-spread-down", path, "intended",
                              f"Narrow the FX spread to {shifted(r, 'fx_spread', '-0.0010')}",
                              f"LK-CONVERTED * {r['fx_spread']}", f"LK-CONVERTED * {shifted(r, 'fx_spread', '-0.0010')}"))
    if Decimal(r["fx_review"]) >= 2000:
        lower = literal(Decimal(r["fx_review"]) / 2, r["fx_review"])
        changes.append(Change("fx-review-down", path, "intended", f"Lower the review threshold to {lower}",
                              f"IF LK-CONVERTED >= {r['fx_review']}", f"IF LK-CONVERTED >= {lower}"))
    return changes


# PURPOSE: CASH MONITORING CHANGES: THE REPORTING BOUNDARY, LOST AGGREGATION, A FIELD TOO SHORT FOR THE TOTAL
def cash_changes(r: dict[str, str], path: str, rule_op: str) -> list[Change]:
    flipped = ">=" if rule_op == ">" else ">"  # from the bank's own rule, so a merged flip is never flipped back as a defect
    threshold = r["cash_threshold"]
    changes = [
        Change("cash-add-compute", path, "refactor", "Write the cash total as a COMPUTE",
               "ADD LK-AMOUNT TO WS-CASH-TOTAL", "COMPUTE WS-CASH-TOTAL = WS-CASH-TOTAL + LK-AMOUNT"),
        Change("cash-kind-reorder", path, "refactor", "List cash out first in the cash test",
               "IF KIND-CASH-IN OR KIND-CASH-OUT", "IF KIND-CASH-OUT OR KIND-CASH-IN"),
        Change("cash-threshold-boundary", path, "defect", "Tidy the cash reporting test",
               f"IF WS-CASH-TOTAL {rule_op} {threshold}", f"IF WS-CASH-TOTAL {flipped} {threshold}"),
        Change("cash-aggregation-dropped", path, "defect", "Start each cash check from zero",
               "MOVE LK-CASH-TODAY TO WS-CASH-TOTAL", "MOVE 0 TO WS-CASH-TOTAL"),
        Change("cash-out-ignored", path, "defect", "Count cash deposits in the daily total",
               "IF KIND-CASH-IN OR KIND-CASH-OUT", "IF KIND-CASH-IN"),
        Change("cash-kind-negated", path, "defect", "State the cash test as not a cheque",
               "IF KIND-CASH-IN OR KIND-CASH-OUT", "IF NOT KIND-CHEQUE"),
        Change("cash-total-narrow", path, "defect", "Shorten the cash total field",
               "WS-CASH-TOTAL           PIC S9(9)V99", "WS-CASH-TOTAL           PIC S9(4)V99"),
        Change("cash-struct-first-deposit", path, "defect", "Simplify the structuring alert",
               "IF KIND-CASH-IN AND LK-CASH-TODAY > 0", "IF KIND-CASH-IN"),
        Change("cash-floor-up", path, "intended",
               f"Raise the structuring alert floor to {shifted(r, 'structuring_floor', '500')}",
               f"AND LK-AMOUNT >= {r['structuring_floor']}",
               f"AND LK-AMOUNT >= {shifted(r, 'structuring_floor', '500')}"),
        Change("cash-threshold-down", path, "intended",
               f"Lower the cash reporting threshold to {shifted(r, 'cash_threshold', '-1000')}",
               f" {threshold}\n", f" {shifted(r, 'cash_threshold', '-1000')}\n", count=2),
    ]
    if Decimal(r["structuring_floor"]) > 1000:
        changes.append(Change("cash-floor-down", path, "intended",
                              f"Lower the structuring alert floor to {shifted(r, 'structuring_floor', '-500')}",
                              f"AND LK-AMOUNT >= {r['structuring_floor']}",
                              f"AND LK-AMOUNT >= {shifted(r, 'structuring_floor', '-500')}"))
    return changes
