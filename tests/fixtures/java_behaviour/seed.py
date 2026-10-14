"""Builds the Java behaviour-check repository: a small rules library, a refactor and a behaviour change.

`refactor` rewrites Rates.bandFor without changing what it returns. `masking` shows five digits of
the card instead of four. MUTATIONS are ten single edits, each a bug a reviewer would want caught,
written before the probe was first run on them (tests/test_java_behaviour.py measures how many the
probe catches).
"""

import importlib.util
import shutil
from pathlib import Path

_spec = importlib.util.spec_from_file_location("change_seed", Path(__file__).resolve().parent.parent / "change" / "seed.py")
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
commit, edit, run = _helpers.commit, _helpers.edit, _helpers.run

SYSTEM = Path(__file__).resolve().parent / "system"
RULES = "src/main/java/com/example/rules"
AUTHOR = ("Ana Costa", "ana.costa@rules.example")
LEAD = "Sam Rivera <sam.rivera@rules.example>"
MUTATIONS = [  # RENAME: (CLASS FILE, TEXT, REPLACEMENT) FOR EACH PLANTED BUG
    ("Limits.java", "return amount > 50000;", "return amount >= 50000;"),
    ("Masking.java", "card.length() < 4", "card.length() < 3"),
    ("Masking.java", "card.substring(card.length() - 4)", "card.substring(card.length() - 3)"),
    ("Rates.java", "amount <= 1000)", "amount < 1000)"),
    ("Rates.java", "return 3;", "return 2;"),
    ("Rates.java", "/ 36500", "/ 36000"),
    ("Calendar.java", "year % 400 == 0", "year % 400 != 0"),
    ("Tally.java", "amount > 0", "amount >= 0"),
    ("Tally.java", "sum += amount;", "sum = amount;"),
    ("Limits.java", "if (value > high) {\n            return high;", "if (value > high) {\n            return low;"),
]


# PURPOSE: CREATES THE REPOSITORY; RETURNS EACH CHANGE'S NAME WITH ITS COMMIT
def seed(root: Path) -> dict[str, str]:
    shutil.copytree(SYSTEM, root)
    rules = root / RULES
    run(root, "init", "-q", "-b", "main")
    shas = {"base": commit(root, AUTHOR, 1, f"RUL-1: Import the rules library\n\nApproved-by: {LEAD}")}
    edit(rules / "Rates.java", "        if (amount <= 1000) {\n            return 1;\n        }\n"
                               "        if (amount <= 10000) {\n            return 2;\n        }\n        return 3;",
         "        return amount <= 1000 ? 1 : amount <= 10000 ? 2 : 3;")
    shas["refactor"] = commit(root, AUTHOR, 2, f"RUL-2: Write the fee bands as one expression\n\nApproved-by: {LEAD}")
    edit(rules / "Masking.java", "card.length() - 4) + card.substring(card.length() - 4)",
         "card.length() - 5) + card.substring(card.length() - 5)")
    shas["masking"] = commit(root, AUTHOR, 3, f"RUL-3: Show five digits on statements\n\nApproved-by: {LEAD}")
    return shas
