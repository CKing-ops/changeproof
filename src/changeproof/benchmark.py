"""Benchmark harness (ROADMAP Week 10): quality, runtime, cost and reproducibility, one file per run."""

import json
import platform
import random
import time
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path

from changeproof.risk import evaluate
from changeproof.signer import digest
from changeproof.solver import BACKENDS, SetCover, brute_force, cover_qubo, greedy_cover, solve

SIZES = ((6, 5), (20, 15), (40, 30), (80, 60))  # RENAME: (ELEMENTS, CANDIDATES) PER SELECTION INSTANCE
TIMED = ("seconds",)  # RENAME: KEYS LEFT OUT OF THE REPRODUCIBILITY DIGEST
BRUTE_FORCE_UP_TO = 20  # RENAME: LARGEST QUBO CHECKED BY TRYING EVERY ASSIGNMENT


# PURPOSE: A SEEDED RANDOM COVER INSTANCE IN WHICH EVERY ELEMENT CAN BE COVERED
def instance(rng: random.Random, elements: int, candidates: int) -> SetCover:
    universe = [f"e{i}" for i in range(elements)]
    sets = {f"t{j}": {e for e in universe if rng.random() < 0.08} for j in range(candidates)}
    for e in universe:
        sets[rng.choice(sorted(sets))].add(e)
    return SetCover(tuple(universe), {k: frozenset(v) for k, v in sets.items()},
                    {k: rng.randint(1, 3) for k in sets})


# PURPOSE: RUNS A SOLVER AND KEEPS ITS OBJECTIVE, OPTIMALITY AND WALL TIME
def timed(solver, problem: SetCover) -> dict:
    start = time.perf_counter()
    found = solver(problem)
    return {"objective": found.objective, "optimal": found.optimal, "selected": len(found.selection),
            "seconds": round(time.perf_counter() - start, 4)}


# PURPOSE: DROPS TIMINGS SO TWO RUNS ON THE SAME INPUTS CAN BE COMPARED
def untimed(value):
    if isinstance(value, dict):
        return {k: untimed(v) for k, v in value.items() if k not in TIMED}
    if isinstance(value, list):
        return [untimed(v) for v in value]
    return value


# PURPOSE: ONE BENCHMARK RUN: TEST SELECTION BY GREEDY AND CP-SAT, THE QUBO CHECK AND THE RISK BASELINE
def run_benchmark(seed: int = 0, sizes: tuple[tuple[int, int], ...] = SIZES) -> dict:
    rng = random.Random(seed)
    rows = []
    for elements, candidates in sizes:
        problem = instance(rng, elements, candidates)
        qubo, _ = cover_qubo(problem)
        check = {"variables": len(qubo.variables)}
        if len(qubo.variables) <= BRUTE_FORCE_UP_TO:
            check["brute_force"] = brute_force(qubo)[0]
        rows.append({"elements": elements, "candidates": candidates, "greedy": timed(greedy_cover, problem),
                     "cp-sat": timed(solve, problem), "qubo": check})
    result = {"seed": seed, "selection": rows, "risk": evaluate(seed),
              "backends": {name: "ran" if b.available else "planned" for name, b in BACKENDS.items()},
              "cost": {"usd": 0, "note": "classical solvers on this machine; nothing was sent anywhere"},
              "environment": {"python": platform.python_version(), "machine": platform.machine(),
                              **{name: version(name) for name in ("ortools", "scikit-learn", "numpy")}}}
    return result | {"digest": digest(json.dumps(untimed(result), sort_keys=True).encode())["sha-384"]}


# PURPOSE: WRITES A RUN TO ITS OWN FILE, NAMED BY TIME AND DIGEST, AND RETURNS THE PATH
def write_run(result: dict, folder: Path) -> Path:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{result['digest'][:12]}.json"
    path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return path
