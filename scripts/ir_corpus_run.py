"""Runs the COBOL adapter over every CardDemo program and records what it extracted.

    uv run python scripts/ir_corpus_run.py > docs/weekly/week02-carddemo-ir.json
"""

import json
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from changeproof.adapters.cobol import CobolAdapter

ROOT = Path(__file__).resolve().parent.parent / "corpus" / "carddemo"
COPYBOOK_DIRS = sorted(  # RENAME: CARDDEMO FOLDERS SEARCHED FOR COPYBOOKS AND DCLGEN MEMBERS
    p.relative_to(ROOT).as_posix() for p in ROOT.glob("app/**/*") if p.is_dir() and p.name in ("cpy", "cpy-bms", "dcl")
)


# PURPOSE: PARSES ONE PROGRAM AND RETURNS ENTITY COUNTS BY KIND, OR THE ERROR
def run_one(path: str) -> dict:
    start = time.process_time()
    try:
        module = CobolAdapter(COPYBOOK_DIRS).parse(Path(path), ROOT)
    except Exception as exc:  # any failure is a result to record, not a crash of the run
        return {"file": Path(path).relative_to(ROOT).as_posix(), "ok": False, "error": str(exc)[:500],
                "cpu_s": round(time.process_time() - start, 1)}
    kinds = Counter(e.kind for e in module.entities)
    return {"file": module.path, "ok": True, "entities": dict(sorted(kinds.items())),
            "cpu_s": round(time.process_time() - start, 1)}


# PURPOSE: RUNS ALL PROGRAMS IN PARALLEL AND PRINTS ONE JSON DOCUMENT
def main() -> int:
    programs = sorted(str(p) for p in ROOT.glob("app/**/*") if p.suffix.lower() == ".cbl")
    with ProcessPoolExecutor() as pool:
        rows = list(pool.map(run_one, programs))
    json.dump({"copybook_dirs": COPYBOOK_DIRS, "programs": rows}, sys.stdout, indent=1)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
