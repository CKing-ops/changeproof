"""Runs every catalogued change of every simulated bank before and after, to check its ground-truth label.

    uv run python scripts/bank_audit.py > docs/weekly/bank-change-audit.json

A defect or intended change must alter at least one probe's output and a refactor none (ADR 016).
Needs GnuCOBOL; no network.
"""

import json
import sys

from changeproof.banksim import BANKS, catalogue
from changeproof.banksim.audit import witness
from changeproof.characterize import LocalRunner


# PURPOSE: AUDITS EVERY BANK'S CATALOGUE AND PRINTS ONE JSON DOCUMENT; EXITS 1 IF ANY LABEL DISAGREES
def main() -> int:
    runner = LocalRunner()
    found = {bank.id: [witness(bank, change, runner) for change in catalogue(bank)] for bank in BANKS}
    wrong = [f"{bank}:{w['change']}" for bank, rows in found.items() for w in rows if not w["agrees"]]
    print(json.dumps({"banks": found, "changes": sum(map(len, found.values())), "disagreements": wrong}, indent=1))
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
