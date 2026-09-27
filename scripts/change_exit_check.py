"""Week 4 exit check: builds the ten-commit seed repository and prints its change records.

    uv run python scripts/change_exit_check.py

Writes docs/weekly/week04-change-records.json. The seed is tests/fixtures/change/seed.py, the same
repository tests/test_change.py checks.
"""

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

from changeproof.change import change_record
from changeproof.config import load_config

ROOT = Path(__file__).resolve().parent.parent
SEED = ROOT / "tests" / "fixtures" / "change" / "seed.py"
REPORT = ROOT / "docs" / "weekly" / "week04-change-records.json"


# PURPOSE: SEEDS THE REPOSITORY, BUILDS A RECORD PER COMMIT AND PRINTS THE REPORT TABLE
def main() -> int:
    spec = importlib.util.spec_from_file_location("seed", SEED)
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    with tempfile.TemporaryDirectory() as scratch:
        root = Path(scratch) / "sepa"
        shas = seed.seed(root)
        config = load_config(root / "changeproof.yaml")
        records = [change_record(root, sha, copybook_dirs=["copy"], config=config, environ={}) for sha in shas]
    REPORT.write_text(json.dumps(
        [r.model_dump(mode="json") | {"gaps": r.gaps(), "open_items": r.open_items()} for r in records], indent=1) + "\n")
    print("| # | Commit | Who (implementer / approver) | What | Why | Gaps | Open items |")
    print("|---|---|---|---|---|---|---|")
    for n, r in enumerate(records, 1):
        changes = {}
        for c in r.what.entities:
            changes[c.change.value] = changes.get(c.change.value, 0) + 1
        what = ", ".join(f"{v} {k}" for k, v in changes.items()) or "no entity changed"
        approvers = ", ".join(a.name for a in r.who.approvers) or "none"
        why = ", ".join(t.id for t in r.why.tickets) or "none"
        if r.why.emergency:
            why += " (emergency)"
        print(f"| {n} | {r.why.subject} | {r.who.implementer.name} / {approvers} | {what} | {why} | "
              f"{'; '.join(r.gaps()) or 'none'} | {'; '.join(r.open_items()) or 'none'} |")
    return 1 if any(r.gaps() for r in records) else 0


if __name__ == "__main__":
    sys.exit(main())
