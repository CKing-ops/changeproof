"""Runs simulated business days for the six synthetic banks (ADR 014).

    uv run python scripts/bank_sim.py --days 1 --keep /mnt/project-files/changeproof/sim

Each day every bank commits one change and the engine scans it. The ledger, scorecard and each
bank's git history are saved to --keep after every day, so the next run, on this machine or a
fresh one, carries on from there. Needs GnuCOBOL; no network.
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

from changeproof.banksim.run import business_day, ledger, restore, save, scorecard

ROOT = Path(__file__).resolve().parent.parent


# PURPOSE: RESTORES THE SIMULATION, RUNS THE ASKED-FOR DAYS AND SAVES AFTER EACH
def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--keep", default=str(ROOT / ".banksim"), help="folder the simulation is saved to")
    parser.add_argument("--workers", type=int, default=3, help="banks scanned side by side")
    args = parser.parse_args()
    keep = Path(args.keep)
    with tempfile.TemporaryDirectory() as scratch:
        state = Path(scratch) / "state"
        restore(state, keep)
        first = max((r["day"] for r in ledger(state)), default=0) + 1
        for day in range(first, first + args.days):
            for row in business_day(state, day, args.workers):
                print(f"day {day} {row['bank']:15} {row['change']:25} {row['truth']['governance']:13} "
                      f"{row['engine']['verdict']:15} {row['outcome']:12} {row['governance']['outcome']:10} "
                      f"{row['seconds']}s", flush=True)
            save(state, keep)
        card = scorecard(ledger(state))
    print(json.dumps({k: card[k] for k in ("days", "changes", "by_outcome", "governance", "seconds")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
