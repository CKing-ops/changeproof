"""Week 9 mutation check: 20 seeded bugs in the three synthetic batch programs.

Written down before the check was first run, one per common mistake: a comparison off by one, a
wrong constant, a changed literal, a loop bound. Each bug carries a witness input on which it
changes what the program returns, so every one is a real behaviour change, not an equivalent edit.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Bug:
    id: str
    program: str
    old: str  # text replaced, exactly once
    new: str
    witness: dict  # linkage inputs on which the bug changes the outputs
    mistake: str


BUGS = [
    Bug("F1", "FEECALC", "IF LK-AMOUNT <= 0", "IF LK-AMOUNT < 0",
        {"LK-AMOUNT": "0", "LK-CUST-TYPE": "P"}, "zero amount no longer rejected"),
    Bug("F2", "FEECALC", "LK-AMOUNT * 0.015", "LK-AMOUNT * 0.016",
        {"LK-AMOUNT": "1000", "LK-CUST-TYPE": "P"}, "personal rate wrong"),
    Bug("F3", "FEECALC", "LK-AMOUNT * 0.010", "LK-AMOUNT * 0.100",
        {"LK-AMOUNT": "1000", "LK-CUST-TYPE": "B"}, "business rate wrong by a factor of ten"),
    Bug("F4", "FEECALC", "IF LK-AMOUNT > 10000", "IF LK-AMOUNT >= 10000",
        {"LK-AMOUNT": "10000", "LK-CUST-TYPE": "P"}, "large-balance discount off by one"),
    Bug("F5", "FEECALC", "IF LK-DAYS-LATE > 30", "IF LK-DAYS-LATE > 31",
        {"LK-AMOUNT": "1000", "LK-CUST-TYPE": "P", "LK-DAYS-LATE": "31"}, "late threshold off by one"),
    Bug("F6", "FEECALC", "ADD 40 TO LK-FEE", "ADD 4 TO LK-FEE",
        {"LK-AMOUNT": "1000", "LK-CUST-TYPE": "P", "LK-DAYS-LATE": "31"}, "late fee mistyped"),
    Bug("F7", "FEECALC", "MOVE 2.50 TO LK-FEE", "MOVE 2.00 TO LK-FEE",
        {"LK-AMOUNT": "1", "LK-CUST-TYPE": "P"}, "minimum fee wrong"),
    Bug("R1", "RISKSCR", "IF LK-LIMIT > 0", "IF LK-LIMIT >= 0",
        {"LK-BALANCE": "0", "LK-LIMIT": "0", "LK-YEARS": "5"}, "zero limit divides instead of scoring as full use"),
    Bug("R2", "RISKSCR", "IF WS-UTIL >= 90", "IF WS-UTIL > 90",
        {"LK-BALANCE": "90", "LK-LIMIT": "100", "LK-YEARS": "5"}, "high-use threshold off by one"),
    Bug("R3", "RISKSCR", "ADD 20 TO WS-SCORE", "ADD 25 TO WS-SCORE",
        {"LK-BALANCE": "50", "LK-LIMIT": "100", "LK-YEARS": "5"}, "medium-use weight wrong"),
    Bug("R4", "RISKSCR", "UNTIL WS-I > LK-MISSED", "UNTIL WS-I >= LK-MISSED",
        {"LK-BALANCE": "0", "LK-LIMIT": "100", "LK-MISSED": "1", "LK-YEARS": "5"}, "loop runs once too few"),
    Bug("R5", "RISKSCR", "IF LK-YEARS < 2", "IF LK-YEARS < 3",
        {"LK-BALANCE": "0", "LK-LIMIT": "100", "LK-YEARS": "2"}, "new-customer threshold off by one"),
    Bug("R6", "RISKSCR", "WHEN WS-SCORE >= 40", "WHEN WS-SCORE > 40",
        {"LK-BALANCE": "90", "LK-LIMIT": "100", "LK-YEARS": "5"}, "grade C boundary off by one"),
    Bug("R7", "RISKSCR", "MOVE 'B' TO LK-GRADE", "MOVE 'A' TO LK-GRADE",
        {"LK-BALANCE": "50", "LK-LIMIT": "100", "LK-YEARS": "5"}, "wrong grade letter"),
    Bug("I1", "INTCALC", "MOVE 0.0425 TO WS-RATE", "MOVE 0.0450 TO WS-RATE",
        {"LK-PRINCIPAL": "10000", "LK-RATE-CODE": "PR", "LK-DAYS": "365"}, "premium rate wrong"),
    Bug("I2", "INTCALC", "IF LK-DAYS = 0", "IF LK-DAYS = 1",
        {"LK-PRINCIPAL": "1000", "LK-RATE-CODE": "ST", "LK-DAYS": "0"}, "zero-day check tests the wrong value"),
    Bug("I3", "INTCALC", "IF LK-DAYS > 365", "IF LK-DAYS > 366",
        {"LK-PRINCIPAL": "10000", "LK-RATE-CODE": "ST", "LK-DAYS": "366"}, "term cap off by one"),
    Bug("I4", "INTCALC", "MOVE 365 TO WS-DAYS", "MOVE 360 TO WS-DAYS",
        {"LK-PRINCIPAL": "10000", "LK-RATE-CODE": "ST", "LK-DAYS": "400"}, "capped term wrong"),
    Bug("I5", "INTCALC", "IF LK-PRINCIPAL >= 100000", "IF LK-PRINCIPAL > 100000",
        {"LK-PRINCIPAL": "100000", "LK-RATE-CODE": "ST", "LK-DAYS": "365"}, "bonus threshold off by one"),
    Bug("I6", "INTCALC", "MOVE 5000 TO LK-INTEREST", "MOVE 500 TO LK-INTEREST",
        {"LK-PRINCIPAL": "1000000", "LK-RATE-CODE": "ST", "LK-DAYS": "365"}, "interest cap mistyped"),
]

# Written after the first run of the check missed four on-point boundary bugs, and before the suite's
# selection was changed. Kept apart so the change can be judged on bugs it was not shaped by.
HELD_OUT = [
    Bug("H1", "FEECALC", "MOVE 'LATE' TO LK-REASON", "MOVE 'LAT' TO LK-REASON",
        {"LK-AMOUNT": "1000", "LK-CUST-TYPE": "P", "LK-DAYS-LATE": "31"}, "reason code truncated"),
    Bug("H2", "FEECALC", "SUBTRACT 25 FROM LK-FEE", "SUBTRACT 25 FROM LK-AMOUNT",
        {"LK-AMOUNT": "20000", "LK-CUST-TYPE": "P"}, "discount applied to the wrong field"),
    Bug("H3", "FEECALC", "IF LK-FEE < 2.50", "IF LK-FEE < 2.00",
        {"LK-AMOUNT": "150", "LK-CUST-TYPE": "P"}, "minimum-fee test uses the wrong amount"),
    Bug("H4", "RISKSCR", "ADD 40 TO WS-SCORE", "ADD 45 TO WS-SCORE",
        {"LK-BALANCE": "95", "LK-LIMIT": "100", "LK-YEARS": "5"}, "high-use weight wrong"),
    Bug("H5", "RISKSCR", "ADD 10 TO WS-SCORE", "ADD 1 TO WS-SCORE",
        {"LK-BALANCE": "0", "LK-LIMIT": "100", "LK-YEARS": "0"}, "new-customer weight mistyped"),
    Bug("H6", "RISKSCR", "WHEN WS-SCORE >= 70", "WHEN WS-SCORE >= 75",
        {"LK-BALANCE": "90", "LK-LIMIT": "100", "LK-MISSED": "2", "LK-YEARS": "5"}, "grade D boundary wrong"),
    Bug("H7", "RISKSCR", "MOVE 100 TO WS-UTIL", "MOVE 0 TO WS-UTIL",
        {"LK-BALANCE": "0", "LK-LIMIT": "0", "LK-YEARS": "5"}, "no-limit accounts scored as unused"),
    Bug("H8", "INTCALC", "MOVE 0.0350 TO WS-RATE", "MOVE 0.0530 TO WS-RATE",
        {"LK-PRINCIPAL": "10000", "LK-RATE-CODE": "ST", "LK-DAYS": "365"}, "standard rate digits swapped"),
    Bug("H9", "INTCALC", "MOVE 'CP' TO LK-STATUS", "MOVE 'OK' TO LK-STATUS",
        {"LK-PRINCIPAL": "1000000", "LK-RATE-CODE": "ST", "LK-DAYS": "365"}, "capped interest not flagged"),
    Bug("H10", "INTCALC", "LK-INTEREST * 1.10", "LK-INTEREST * 1.01",
        {"LK-PRINCIPAL": "100000", "LK-RATE-CODE": "ST", "LK-DAYS": "365"}, "bonus factor mistyped"),
]


# PURPOSE: A PROGRAM'S SOURCE WITH ONE BUG APPLIED
def apply(source: str, bug: Bug) -> str:
    if source.count(bug.old) != 1:
        raise ValueError(f"{bug.id}: '{bug.old}' must appear exactly once")
    return source.replace(bug.old, bug.new)
