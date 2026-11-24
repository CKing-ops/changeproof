"""Checks each catalogued change's ground truth by running it, so the scoring never rests on a label alone.

The base and changed program are run on the same probe inputs under GnuCOBOL. A defect or intended
change must give a different output on at least one probe; a refactor must give the same output on
every probe. Probes are boundary values taken from the bank's rules plus seeded random draws, so a
refactor's "same" is a sampled check, not a proof.
"""

import random
import tempfile
from decimal import Decimal
from pathlib import Path

from changeproof.banksim.banks import Bank
from changeproof.banksim.estate import BEHAVIOUR, Change, current, render
from changeproof.banksim.operations import FOREIGN, UNQUOTED, run_rows

DRAWS = 120  # RENAME: RANDOM PROBES PER PROGRAM ON TOP OF THE BOUNDARY ONES


# PURPOSE: A VALUE ONE CENT (OR ONE UNIT) EITHER SIDE OF A LITERAL, AND THE LITERAL ITSELF
def around(value: str) -> list[str]:
    step = Decimal(1).scaleb(-len(value.split(".")[1])) if "." in value else Decimal(1)
    return [str(Decimal(value) + d * step) for d in (-1, 0, 1)]


# PURPOSE: A RANDOM MONEY AMOUNT WITH CENTS
def cents(rng: random.Random, high: float) -> str:
    return f"{rng.uniform(0.01, high):.2f}"


# PURPOSE: PROBE INPUTS FOR ONE PROGRAM: EVERY RULE BOUNDARY CROSSED WITH THE CODES THAT PICK A PATH, PLUS RANDOM DRAWS
def probes(bank: Bank, program: str, rules: dict[str, str]) -> list[dict]:
    rng = random.Random(f"{bank.id}:probes:{program}")
    r = rules
    if program == "INTACCR":
        edges = [{"LK-BALANCE": b, "LK-DAYS": d, "LK-PRODUCT": p} for b in around(r["tier"]) + ["0.00", "-5.00"]
                 for d in ("1", r["max_days"], str(int(r["max_days"]) + 1)) for p in "SCX"]
        draws = [{"LK-BALANCE": cents(rng, 90000), "LK-DAYS": str(rng.randint(1, 40)), "LK-PRODUCT": rng.choice("SC")}
                 for _ in range(DRAWS)]
    elif program == "FEEASSES":
        edges = [{"LK-AVG-BALANCE": b, "LK-TXN-COUNT": n, "LK-SEGMENT": s} for b in around(r["retail_minimum"])
                 for n in around(r["free_txns"]) + ["0", str(int(r["free_txns"]) + 37)] for s in "RBSX"]
        draws = [{"LK-AVG-BALANCE": cents(rng, 9000), "LK-TXN-COUNT": str(rng.randint(0, 400)),
                  "LK-SEGMENT": rng.choice("RBS")} for _ in range(DRAWS)]
    elif program == "PAYSCRN":
        edges = [{"LK-AMOUNT": a, "LK-CURRENCY": bank.currency, "LK-DAILY-USED": u, "LK-CHANNEL": c}
                 for a in around(r["report_threshold"]) + ["0.00", "100.00"]
                 for u in ("0.00", str(Decimal(r["online_limit"]) - 100), str(Decimal(r["branch_limit"]) - 100))
                 for c in "OB"]
        edges.append({"LK-AMOUNT": "50.00", "LK-CURRENCY": FOREIGN[bank.currency][0], "LK-DAILY-USED": "0.00",
                      "LK-CHANNEL": "O"})
        draws = [{"LK-AMOUNT": cents(rng, 30000), "LK-CURRENCY": bank.currency, "LK-DAILY-USED": cents(rng, 60000),
                  "LK-CHANNEL": rng.choice("OB")} for _ in range(DRAWS)]
    elif program == "LOANPMT":
        grace, late = int(r["grace_days"]), int(r["delinquent_days"])
        days = sorted({0, grace, grace + 1, grace + 5, grace + 6, max(grace - 5, 0), max(grace - 4, 0),
                       late - 1, late, late + 1})
        edges = [{"LK-PRINCIPAL": "12345.67", "LK-PAYMENT": pay, "LK-DAYS-LATE": str(d), "LK-LOAN-TYPE": t}
                 for pay in ("90.00", "333.33", "1234.56", "9999.99") for d in days for t in "MAPX"]
        draws = [{"LK-PRINCIPAL": cents(rng, 400000), "LK-PAYMENT": cents(rng, 3000),
                  "LK-DAYS-LATE": str(rng.randint(0, 90)), "LK-LOAN-TYPE": rng.choice("MAP")} for _ in range(DRAWS)]
    elif program == "FXCONV":
        quoted = (r["fx1"], r["fx2"], r["fx3"])
        edges = [{"LK-AMOUNT": a, "LK-FROM-CCY": c, "LK-CUSTOMER": k}
                 for a in ["0.00", "1.00", "123.45", "999.99", "4321.09"]
                 + [str((Decimal(v) / Decimal(r["fx1_rate"])).quantize(Decimal("0.01"))) for v in around(r["fx_review"])]
                 + [str(Decimal(v) * 2) for v in around(r["fx_review"])]
                 for c in (*quoted, UNQUOTED[0]) for k in "PS"]
        draws = [{"LK-AMOUNT": cents(rng, 80000), "LK-FROM-CCY": rng.choice(quoted), "LK-CUSTOMER": rng.choice("PS")}
                 for _ in range(DRAWS)]
    elif program == "CASHAGG":
        threshold, floor = r["cash_threshold"], r["structuring_floor"]
        amounts = around(threshold) + around(floor) + around(str(Decimal(threshold) - 1000)) \
            + around(str(Decimal(floor) + 500)) + around(str(Decimal(floor) - 500)) + ["600.00", "60000.00"]
        edges = [{"LK-AMOUNT": a, "LK-KIND": k, "LK-CASH-TODAY": t}
                 for a in amounts for k in "IOQX" for t in ("0.00", "500.00", "9999.00")]
        draws = [{"LK-AMOUNT": cents(rng, 20000), "LK-KIND": rng.choice("IOQ"), "LK-CASH-TODAY": cents(rng, 20000)}
                 for _ in range(DRAWS)]
    else:
        edges = [{"TRAN-FILE:records": "1", "TRAN-ACCT-ID": "100001", "TRAN-TYPE": t, "TRAN-AMOUNT": a,
                  "ACCT-FILE:records": "1", "ACCT-ID": acct, "ACCT-BALANCE": b, "ACCT-LIMIT": "500.00"}
                 for t in "CDX" for a in ("50.00", "400.00", "900.00") for b in ("100.00", "-50.00")
                 for acct in ("100001", "100002")]
        draws = []
    return edges + draws


# PURPOSE: HOW MANY PROBES GIVE A DIFFERENT OUTPUT BEFORE AND AFTER A CHANGE, AND WHETHER THAT MATCHES ITS LABEL
def witness(bank: Bank, change: Change, runner, root: Path | None = None) -> dict:
    with tempfile.TemporaryDirectory() as scratch:
        before, after = Path(scratch) / "before", Path(scratch) / "after"
        render(bank, before)
        if root:
            for path in (root / "src").glob("*.cbl"):
                (before / "src" / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        source = before / change.path
        if change.old not in source.read_text(encoding="utf-8"):  # a change written back needs its forward one first
            source.write_text(source.read_text(encoding="utf-8").replace(change.new, change.old), encoding="utf-8")
        render(bank, after)
        for path in (before / "src").glob("*.cbl"):
            (after / "src" / path.name).write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        target = after / change.path
        target.write_text(target.read_text(encoding="utf-8").replace(change.old, change.new), encoding="utf-8")
        program = Path(change.path).stem
        rows = probes(bank, program, current(bank, before))
        old, new = run_rows(before, program, rows, runner), run_rows(after, program, rows, runner)
    different = sum(a != b for a, b in zip(old, new))
    agrees = (different > 0) == (BEHAVIOUR[change.kind] == "different")
    return {"change": change.id, "kind": change.kind, "probes": len(rows), "different": different, "agrees": agrees}
