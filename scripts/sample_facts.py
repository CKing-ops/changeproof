"""Draws the Week 2 exit-check sample: 20 IR facts from real CardDemo programs, with the source
line each one cites, so a person can check the provenance by eye.

    uv run python scripts/sample_facts.py
"""

import json
import random
import sys
from pathlib import Path

from changeproof.adapters.cobol import CobolAdapter

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "carddemo"
PROGRAMS = [  # RENAME: PROGRAMS THE SAMPLE IS DRAWN FROM (BATCH, CICS, CICS WITH DB2 AND REPLACING)
    "app/cbl/CBACT01C.cbl",
    "app/cbl/COSGN00C.cbl",
    "app/app-transaction-type-db2/cbl/COTRTUPC.cbl",
]
COPYBOOK_DIRS = [
    "app/cpy", "app/cpy-bms",
    "app/app-transaction-type-db2/cpy", "app/app-transaction-type-db2/cpy-bms", "app/app-transaction-type-db2/dcl",
]
SAMPLE_SIZE = 20  # RENAME: FACTS IN THE EXIT-CHECK SAMPLE
SEED = 2  # RENAME: FIXED SEED SO THE SAMPLE IS REPRODUCIBLE
GOLDEN = ROOT / "tests" / "fixtures" / "exit_check" / "week02_facts.json"


# PURPOSE: PICKS FACTS ROUND-ROBIN ACROSS KINDS SO EVERY KIND OF FACT GETS CHECKED
def stratified(entities: list, size: int, rng: random.Random) -> list:
    by_kind: dict[str, list] = {}
    for entity in entities:
        by_kind.setdefault(entity.kind, []).append(entity)
    for bucket in by_kind.values():
        rng.shuffle(bucket)
    picked = []
    while len(picked) < size and any(by_kind.values()):
        for kind in sorted(by_kind):
            if by_kind[kind] and len(picked) < size:
                picked.append(by_kind[kind].pop())
    return picked


# PURPOSE: PARSES THE PROGRAMS, DRAWS THE SAMPLE, WRITES THE GOLDEN FILE AND PRINTS THE TABLE
def main() -> int:
    adapter = CobolAdapter(COPYBOOK_DIRS)
    entities = [e for program in PROGRAMS for e in adapter.parse(CORPUS / program, CORPUS).entities]
    sample = stratified(entities, SAMPLE_SIZE, random.Random(SEED))
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps([{"id": e.id, "kind": e.kind, "provenance": str(e.provenance)} for e in sample],
                                 indent=1) + "\n")
    print("| # | Fact | Provenance | Source line (columns 8-72) |")
    print("|---|---|---|---|")
    for n, e in enumerate(sample, 1):
        line = (CORPUS / e.provenance.file).read_text(encoding="latin-1").splitlines()[e.provenance.line - 1]
        print(f"| {n} | `{e.id}` | `corpus/carddemo/{e.provenance}` | `{line[7:72].strip()}` |")
    return 0


if __name__ == "__main__":
    sys.exit(main())
