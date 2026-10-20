"""A bank's customers and the work its programs do for them each simulated day.

Every bank has a book of invented accounts. Each day interest accrues on every account, customers
post deposits and withdrawals, payments are screened, and fees are charged at month end. The bank's
own COBOL programs do that work, run under GnuCOBOL, and their results move the balances, so a
defect that reaches main shows up in the bank's numbers the next day.
"""

import calendar
import json
import random
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from changeproof.adapters.cobol import CobolAdapter
from changeproof.banksim.banks import Bank

ACCOUNTS = 300  # RENAME: ACCOUNTS ON EACH BANK'S BOOK
FIRST_ID = 100001  # RENAME: FIRST ACCOUNT NUMBER
FOREIGN = {"USD": ("EUR", "GBP", "CAD"), "EUR": ("USD", "GBP", "CHF")}  # RENAME: CURRENCIES A PAYMENT MAY ARRIVE IN
CENT = Decimal("0.01")


@dataclass
class Account:
    id: int
    product: str  # S savings, C checking
    segment: str  # R retail, B business, S student
    balance: str
    limit: str
    month_txns: int = 0


# PURPOSE: A MONEY AMOUNT FROM A LOG-NORMAL DRAW AROUND A MEDIAN, KEPT INSIDE A FIELD'S RANGE
def money(rng: random.Random, median: float, spread: float, cap: float) -> str:
    return str(Decimal(min(rng.lognormvariate(0, spread) * median, cap)).quantize(CENT))


# PURPOSE: THE BANK'S BOOK ON ITS FIRST DAY, THE SAME EVERY TIME FOR THE SAME BANK
def open_accounts(bank: Bank) -> list[Account]:
    rng = random.Random(f"{bank.id}:accounts")
    book = []
    for n in range(ACCOUNTS):
        segment = rng.choices("RBS", weights=(78, 14, 8))[0]
        product = rng.choices("SC", weights=(55, 45))[0]
        median = {"R": 3500, "B": 40000, "S": 600}[segment]
        limits = {"R": (0, 500, 1000, 2500), "B": (5000, 10000), "S": (0, 250)}[segment]
        book.append(Account(FIRST_ID + n, product, segment, money(rng, median, 1.1, 9_000_000),
                            str(rng.choice(limits)) if product == "C" else "0"))
    return book


# PURPOSE: TRUE ON THE LAST CALENDAR DAY OF A MONTH, WHEN FEES ARE CHARGED
def month_end(day: date) -> bool:
    return day.day == calendar.monthrange(day.year, day.month)[1]


# PURPOSE: THE DAY'S INPUT ROWS FOR EACH PROGRAM, DRAWN FROM THE BOOK AND THE DATE
def traffic(bank: Bank, book: list[Account], day_number: int, on: date) -> dict[str, list[dict]]:
    rng = random.Random(f"{bank.id}:ops:{day_number}")
    weekend = on.weekday() >= 5
    interest = [{"LK-BALANCE": a.balance, "LK-DAYS": "1", "LK-PRODUCT": a.product} for a in book]
    postings = []
    for _ in range(rng.randint(5, 10) if weekend else rng.randint(25, 45)):
        account = rng.choice(book)
        unknown = rng.random() < 0.02
        postings.append({
            "TRAN-FILE:records": "1", "TRAN-ACCT-ID": str(account.id + (ACCOUNTS if unknown else 0)),
            "TRAN-TYPE": rng.choices("CDX", weights=(45, 53, 2))[0],
            "TRAN-AMOUNT": money(rng, 2000 if account.segment == "B" else 120, 1.0, 900_000),
            "ACCT-FILE:records": "1", "ACCT-ID": str(account.id), "ACCT-BALANCE": account.balance,
            "ACCT-LIMIT": account.limit})
    payments = []
    for _ in range(rng.randint(3, 8) if weekend else rng.randint(15, 30)):
        large = rng.random() < 0.05
        payments.append({
            "LK-AMOUNT": money(rng, 10000 if large else 900, 0.3 if large else 1.2, 9_000_000),
            "LK-CURRENCY": bank.currency if rng.random() < 0.94 else rng.choice(FOREIGN[bank.currency]),
            "LK-DAILY-USED": money(rng, 1500, 1.3, 9_000_000), "LK-CHANNEL": rng.choices("OB", weights=(70, 30))[0]})
    fees = [{"LK-AVG-BALANCE": a.balance, "LK-TXN-COUNT": str(a.month_txns), "LK-SEGMENT": a.segment}
            for a in book] if month_end(on) else []
    return {"INTACCR": interest, "POSTTXN": postings, "PAYSCRN": payments, "FEEASSES": fees}


# PURPOSE: RUNS ONE PROGRAM IN A SOURCE TREE ON A LIST OF INPUT ROWS; RETURNS EACH RUN'S OUTPUT WITH ITS RC
def run_rows(tree: Path, program: str, rows: list[dict], runner) -> list[dict]:
    if not rows:
        return []
    adapter = CobolAdapter([], root=tree, runner=runner)
    module = adapter.parse(tree / "src" / f"{program}.cbl", tree)
    defaults = {f.key: f.default for f in adapter.inputs(module)}
    return [run.output | {"rc": run.rc} for run in adapter.execute(module, [defaults | r for r in rows])[1]]


# PURPOSE: MOVES THE BOOK BY WHAT THE PROGRAMS DID AND TOTALS THE DAY'S BUSINESS
def settle(book: list[Account], rows: dict[str, list[dict]], results: dict[str, list[dict]], on: date) -> dict:
    by_id = {a.id: a for a in book}
    interest = Decimal(0)
    for a, out in zip(book, results["INTACCR"]):
        interest += Decimal(out["LK-INTEREST"])
        a.balance = str(Decimal(a.balance) + Decimal(out["LK-INTEREST"]))
    posted = rejected = 0
    for row, out in zip(rows["POSTTXN"], results["POSTTXN"]):
        account = by_id[int(row["ACCT-ID"])]
        account.month_txns += 1
        if "ACCT-FILE#00001.ACCT-BALANCE" in out:
            account.balance = str(Decimal(out["ACCT-FILE#00001.ACCT-BALANCE"]))
        posted += "POSTED 00001" in out["SYSOUT"]
        rejected += "REJECTED 00001" in out["SYSOUT"]
    fees = Decimal(0)
    waived = 0
    for a, out in zip(book, results["FEEASSES"]):
        fees += Decimal(out["LK-FEE"])
        waived += out["LK-WAIVED"] == "Y"
        a.balance = str(Decimal(a.balance) - Decimal(out["LK-FEE"]))
        a.month_txns = 0
    decisions = Counter(out["LK-DECISION"].strip() for out in results["PAYSCRN"])
    return {"date": str(on), "accounts": len(book), "deposits": str(sum(Decimal(a.balance) for a in book)),
            "overdrawn": sum(Decimal(a.balance) < 0 for a in book), "interest": str(interest),
            "postings": len(rows["POSTTXN"]), "posted": posted, "rejected": rejected,
            "payments": len(rows["PAYSCRN"]), "decisions": dict(sorted(decisions.items())),
            "reported": sum(out["LK-REPORT"] == "Y" for out in results["PAYSCRN"]),
            "fees": str(fees) if results["FEEASSES"] else None, "waived": waived}


# PURPOSE: THE BANK'S BOOK FROM THE STATE FOLDER, OPENED FRESH ON FIRST USE
def load_book(bank: Bank, state: Path) -> list[Account]:
    path = state / "accounts" / f"{bank.id}.json"
    if not path.exists():
        return open_accounts(bank)
    return [Account(**a) for a in json.loads(path.read_text(encoding="utf-8"))]


# PURPOSE: WRITES THE BANK'S BOOK TO THE STATE FOLDER
def save_book(bank: Bank, state: Path, book: list[Account]) -> None:
    (state / "accounts").mkdir(parents=True, exist_ok=True)
    (state / "accounts" / f"{bank.id}.json").write_text(json.dumps([asdict(a) for a in book]) + "\n",
                                                        encoding="utf-8")
