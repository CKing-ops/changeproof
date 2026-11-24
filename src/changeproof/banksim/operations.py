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
UNQUOTED = ("JPY", "AUD", "SEK")  # RENAME: CURRENCIES NO BANK HAS A RATE FOR
LOANS = {"M": (220000, 25), "A": (18000, 5), "P": (6000, 3)}  # RENAME: LOAN TYPE TO MEDIAN PRINCIPAL AND TERM IN YEARS
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
    for _ in range(rng.randint(8, 16) if weekend else rng.randint(40, 80)):
        account = rng.choice(book)
        unknown = rng.random() < 0.02
        postings.append({
            "TRAN-FILE:records": "1", "TRAN-ACCT-ID": str(account.id + (ACCOUNTS if unknown else 0)),
            "TRAN-TYPE": rng.choices("CDX", weights=(45, 53, 2))[0],
            "TRAN-AMOUNT": money(rng, 2000 if account.segment == "B" else 120, 1.0, 900_000),
            "ACCT-FILE:records": "1", "ACCT-ID": str(account.id), "ACCT-BALANCE": account.balance,
            "ACCT-LIMIT": account.limit})
    payments = []
    for _ in range(rng.randint(5, 12) if weekend else rng.randint(25, 50)):
        large = rng.random() < 0.05
        payments.append({
            "LK-AMOUNT": money(rng, 10000 if large else 900, 0.3 if large else 1.2, 9_000_000),
            "LK-CURRENCY": bank.currency if rng.random() < 0.94 else rng.choice(FOREIGN[bank.currency]),
            "LK-DAILY-USED": money(rng, 1500, 1.3, 9_000_000), "LK-CHANNEL": rng.choices("OB", weights=(70, 30))[0]})
    fees = [{"LK-AVG-BALANCE": a.balance, "LK-TXN-COUNT": str(a.month_txns), "LK-SEGMENT": a.segment}
            for a in book] if month_end(on) else []
    return {"INTACCR": interest, "POSTTXN": postings, "PAYSCRN": payments, "FEEASSES": fees,
            "LOANPMT": installments(bank, rng, weekend), "FXCONV": conversions(bank, rng, weekend),
            "CASHAGG": cash(bank, book, rng, weekend)}


# PURPOSE: THE DAY'S LOAN INSTALLMENTS: MOSTLY ON TIME, SOME LATE OR SHORT, A FEW ON A LOAN TYPE THE BANK DOES NOT OFFER
def installments(bank: Bank, rng: random.Random, weekend: bool) -> list[dict]:
    rows = []
    for _ in range(rng.randint(2, 6) if weekend else rng.randint(12, 30)):
        kind = rng.choices("MAPX", weights=(30, 40, 29, 1))[0]
        median, years = LOANS.get(kind, LOANS["P"])
        principal = Decimal(money(rng, median, 0.7, 9_000_000))
        due = (principal / (years * 12) + principal * Decimal("0.06") / 12).quantize(CENT)
        paid = due if rng.random() < 0.93 else (due * Decimal(rng.uniform(0.05, 0.9))).quantize(CENT)
        late = rng.choices((0, rng.randint(1, 20), rng.randint(21, 45), rng.randint(46, 120)),
                           weights=(80, 12, 5, 3))[0]
        rows.append({"LK-PRINCIPAL": str(principal), "LK-PAYMENT": str(min(paid, Decimal("9999999.99"))),
                     "LK-DAYS-LATE": str(late), "LK-LOAN-TYPE": kind})
    return rows


# PURPOSE: THE DAY'S FOREIGN CURRENCY CONVERSIONS, SOME IN ROUND AMOUNTS AND A FEW IN CURRENCIES WITHOUT A RATE
def conversions(bank: Bank, rng: random.Random, weekend: bool) -> list[dict]:
    rows = []
    for _ in range(rng.randint(1, 5) if weekend else rng.randint(8, 20)):
        large = rng.random() < 0.05
        amount = money(rng, 60000 if large else 1500, 0.6 if large else 1.2, 9_000_000)
        if rng.random() < 0.2:
            amount = str(Decimal(amount).quantize(Decimal(100)).quantize(CENT) or Decimal("100.00"))
        rows.append({"LK-AMOUNT": amount,
                     "LK-FROM-CCY": rng.choice(UNQUOTED) if rng.random() < 0.03 else rng.choice(FOREIGN[bank.currency]),
                     "LK-CUSTOMER": "P" if rng.random() < 0.15 else "S"})
    return rows


# Some customers split deposits just under the reporting threshold and some bring exactly the threshold.
# PURPOSE: THE DAY'S CASH IN AND OUT, EACH ROW CARRYING THE CUSTOMER'S EARLIER SAME-DIRECTION CASH THAT DAY
def cash(bank: Bank, book: list[Account], rng: random.Random, weekend: bool) -> list[dict]:
    threshold = Decimal(bank.rules["cash_threshold"])
    floor = Decimal(bank.rules["structuring_floor"])
    rows, earlier = [], Counter()
    for _ in range(rng.randint(4, 10) if weekend else rng.randint(20, 40)):
        account = rng.choice(book)
        kind = rng.choices("IOQ", weights=(55, 35, 10))[0]
        pattern = rng.random()
        if pattern < 0.06:
            amounts = [str((floor + (threshold - floor) * Decimal(rng.uniform(0, 0.99))).quantize(CENT))
                       for _ in range(rng.randint(2, 3))]
            kind = "I"
        elif pattern < 0.09:
            amounts = [str(threshold)]
        else:
            amounts = [money(rng, 4000 if account.segment == "B" else 600, 1.1, 9_000_000)]
        for value in amounts:
            rows.append({"LK-AMOUNT": str(min(Decimal(value), Decimal("9999999.99"))), "LK-KIND": kind,
                         "LK-CASH-TODAY": str(earlier[account.id, kind])})
            if kind != "Q":
                earlier[account.id, kind] += Decimal(value)
    return rows


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
    loans = results.get("LOANPMT", [])
    conversions = results.get("FXCONV", [])
    cash = results.get("CASHAGG", [])
    return {"date": str(on), "accounts": len(book), "deposits": str(sum(Decimal(a.balance) for a in book)),
            "overdrawn": sum(Decimal(a.balance) < 0 for a in book), "interest": str(interest),
            "postings": len(rows["POSTTXN"]), "posted": posted, "rejected": rejected,
            "payments": len(rows["PAYSCRN"]), "decisions": dict(sorted(decisions.items())),
            "reported": sum(out["LK-REPORT"] == "Y" for out in results["PAYSCRN"]),
            "fees": str(fees) if results["FEEASSES"] else None, "waived": waived,
            "loans": {"installments": len(loans), "interest": str(total(loans, "LK-INTEREST")),
                      "late_fees": str(total(loans, "LK-LATE-FEE")),
                      "status": dict(sorted(Counter(o["LK-STATUS"].strip() for o in loans).items()))},
            "fx": {"conversions": len(conversions), "converted": str(total(conversions, "LK-CONVERTED")),
                   "fees": str(total(conversions, "LK-FX-FEE")),
                   "decisions": dict(sorted(Counter(o["LK-DECISION"].strip() for o in conversions).items()))},
            "cash": {"transactions": len(cash), "reported": sum(o["LK-REPORT"] == "Y" for o in cash),
                     "structuring_alerts": sum(o["LK-ALERT"].strip() == "STRUCT" for o in cash)}}


# PURPOSE: THE SUM OF ONE MONEY OUTPUT OVER A PROGRAM'S RUNS
def total(runs: list[dict], field: str) -> Decimal:
    return sum((Decimal(o[field]) for o in runs), Decimal(0))


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
