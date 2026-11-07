import json
import re
from collections import Counter
from decimal import Decimal
from itertools import combinations
from pathlib import Path

from changeproof.adapters.base import Entity, IRModule
from changeproof.adapters.cobol import CobolAdapter
from changeproof.adapters.cobol.driver import Field, boundary_values, candidates, linkage_fields, parse_picture
from changeproof.adapters.cobol.gnucobol import DockerRunner, LocalRunner, Run, Runner, read_trace
from changeproof.signer import digest

__all__ = ["DockerRunner", "LocalRunner", "Runner", "around", "candidates", "characterize", "input_fields",
           "linkage_fields", "outcomes", "output_digest", "pairs", "parse_picture", "read_trace", "replay", "rerun"]

MAX_ROUNDS = 6  # RENAME: SEARCH ROUNDS BEFORE GIVING UP ON AN OUTCOME NO INPUT HAS REACHED
PAIR_SEEDS = 3  # RENAME: RUNS PER CONDITION THE PAIRWISE ROUND STARTS FROM
PAIR_BUDGET = 3000  # RENAME: MOST RUNS THE PAIRWISE ROUND MAY ADD TO ONE PROGRAM'S SEARCH
NUMBER = re.compile(r"-?\d+(\.\d+)?")
HUNG = 124  # exit code of a run stopped by its timeout


# PURPOSE: WHICH WAYS A BRANCH WENT IN ONE RUN, READ FROM HOW OFTEN ITS LINES RAN
def outcomes(branch: Entity, lines: Counter) -> set[bool]:
    a = branch.attributes  # RENAME: BRANCH ATTRIBUTES
    decision = a.get("decision_line", branch.provenance.line)
    if not lines[decision]:
        return set()
    found = set()
    # a loop that ran to the end met its UNTIL condition
    if a["kind"] == "until" or (a["true_line"] and lines[a["true_line"]]):
        found.add(True)
    if a["false_line"]:
        if lines[a["false_line"]]:
            found.add(False)
    elif a["true_line"] and lines[decision] > lines[a["true_line"]]:
        found.add(False)
    return found


# PURPOSE: EVERY (BRANCH, OUTCOME) PAIR ONE RUN REACHED
def reached(branches: list[Entity], lines: Counter) -> set[tuple[str, bool]]:
    return {(b.id, o) for b in branches for o in outcomes(b, lines)}


# PURPOSE: INPUT SETS THAT CHANGE ONE FIELD OF A SEED TO EACH OF ITS BOUNDARY VALUES
def variants(seed: dict[str, str], pools: dict[str, list[str]]) -> list[dict[str, str]]:
    return [seed | {name: value} for name, pool in pools.items() if len(pool) > 1 for value in pool]


# PURPOSE: INPUT SETS THAT CHANGE TWO FIELDS OF A SEED TOGETHER, OVER EVERY PAIR OF THEIR VALUES
def pairs(seed: dict[str, str], pools: dict[str, list[str]], names: list[str]) -> list[dict[str, str]]:
    return [seed | {a: x, b: y} for a, b in combinations(names, 2) for x in pools[a] for y in pools[b]]


# PURPOSE: A VALUE AND, WHEN IT IS A NUMBER, THE NUMBERS ONE UNIT OF ITS LAST DIGIT EITHER SIDE
def neighbours(value: str) -> list[str]:
    if not NUMBER.fullmatch(value):
        return [value]
    n = Decimal(value)
    unit = Decimal(1).scaleb(n.as_tuple().exponent)
    return [format(n - unit, "f"), value, format(n + unit, "f")]


# PURPOSE: EACH ON-POINT VALUE AND ITS NEIGHBOURS ONE UNIT EITHER SIDE THAT THE FIELD'S POOL HOLDS, WITH THE BRANCHES
def around(bounds: dict[str, dict[str, set[str]]], pools: dict[str, list[str]]) -> dict[str, dict[str, set[str]]]:
    found: dict[str, dict[str, set[str]]] = {}  # RENAME: FIELD TO VALUE NEAR A LITERAL TO THE BRANCHES COMPARING THEM
    for name, points in bounds.items():
        pool = set(pools[name])
        for value, branch_ids in points.items():
            for near in neighbours(value):
                if near in pool:
                    found.setdefault(name, {}).setdefault(near, set()).update(branch_ids)
    return found


# PURPOSE: (FIELD, VALUE, CONDITION) FOR EACH INPUT SITTING EXACTLY ON A LITERAL A CONDITION THAT RAN COMPARED IT WITH
def boundary_hits(inputs: dict[str, str], bounds: dict[str, dict[str, set[str]]], got: set) -> set[tuple[str, str, str]]:
    ran = {branch for branch, _ in got}
    return {(name, value, branch) for name, value in inputs.items()
            for branch in bounds.get(name, {}).get(value, set()) & ran}


# PURPOSE: (FIELD, VALUE) PAIRS OF A RUN THAT SAT ON OR NEXT TO A LITERAL A CONDITION THAT RAN COMPARED THE FIELD WITH
def near_points(inputs: dict[str, str], near: dict[str, dict[str, set[str]]], got: set) -> set[tuple[str, str]]:
    return {(name, value) for name, value, _ in boundary_hits(inputs, near, got)}


# PURPOSE: BOUNDARY SEARCH, KEEPING THE FIRST RUN DOWN EACH PATH AND THE FIRST RUN ON OR NEXT TO EACH BOUNDARY POINT
def search(adapter: CobolAdapter, module: IRModule, branches: list[Entity], pools: dict[str, list[str]],
           bounds: dict[str, dict[str, set[str]]], batch: bool = False) -> tuple[list, int]:
    near = around(bounds, pools)
    goal = {(b.id, o) for b in branches for o in (True, False)}
    tried, results, covered = set(), [], set()

    # PURPOSE: RUNS THE INPUT SETS NOT TRIED BEFORE; NONE WHEN ALL WERE, ELSE THE ONES THAT REACHED A NEW OUTCOME
    def attempt(todo: list[dict[str, str]]) -> list[dict[str, str]] | None:
        fresh = []  # RENAME: INPUT SETS NOT RUN BEFORE
        for inputs in todo:
            if (key := tuple(sorted(inputs.items()))) not in tried:
                tried.add(key)
                fresh.append(inputs)
        if not fresh:
            return None
        _, runs = adapter.execute(module, fresh)
        seeds = []
        for inputs, run in zip(fresh, runs):
            # a batch job's return code is part of its behaviour; a subprogram's driver only fails when the call did
            if run.rc == HUNG or (run.rc and not batch):
                continue
            got = reached(branches, run.lines)
            if got - covered:
                seeds.append(inputs)
                covered.update(got)
            results.append((inputs, run, got))
        return seeds

    # PURPOSE: WHAT A CONDITION STILL LACKS: AN OUTCOME NO RUN TOOK, OR A VALUE NEAR ITS LITERAL NO RUN REACHING IT HELD
    def open_at(branch: str) -> bool:
        if {(branch, True), (branch, False)} - covered:
            return True
        want = {(n, v) for n, values in near.items() for v, ids in values.items() if branch in ids}
        held = {(n, inputs[n]) for inputs, _, got in results if any(b == branch for b, _ in got) for n in near}
        return bool(want - held)

    bases = [{n: p[0] for n, p in pools.items()}, {n: p[len(p) // 2] for n, p in pools.items()},
             {n: p[-1] for n, p in pools.items()}]
    todo = bases + [v for b in bases for v in variants(b, pools)]
    for _ in range(MAX_ROUNDS):
        seeds = attempt(todo)
        if seeds is None or covered >= goal:
            break
        todo = [v for s in seeds for v in variants(s, pools)]
    # one field at a time misses paths that need a balance, an amount and a limit set together, and boundaries
    # behind a guard that the first runs met from the wrong side; start again from runs that reached each condition
    names = [n for n in near if len(pools[n]) > 1]  # RENAME: FIELDS A CONDITION COMPARES WITH A LITERAL
    budget = len(tried) + PAIR_BUDGET
    for branch in branches:
        if not open_at(branch.id):
            continue
        starts = {}  # RENAME: PATH TO THE FIRST RUN DOWN IT THAT REACHED THIS CONDITION
        for inputs, _, got in results:
            if any(b == branch.id for b, _ in got):
                starts.setdefault(frozenset(got), inputs)
        starts = list(starts.values())[:PAIR_SEEDS]
        attempt([v for s in starts for v in variants(s, {n: pools[n] for n in names})])
        for seed in starts:
            if not open_at(branch.id) or len(tried) >= budget:
                break
            attempt(pairs(seed, pools, names)[:budget - len(tried)])
    paths = {}  # RENAME: SET OF OUTCOMES A RUN REACHED TO THE FIRST RUN THAT TOOK THAT PATH
    for result in results:
        paths.setdefault(frozenset(result[2]), result)
    chosen = list(paths.values())
    # a run on or one step past a literal catches an off-by-one, and arithmetic the on-point run multiplies by zero
    points = {p for inputs, _, got in chosen for p in near_points(inputs, near, got)}
    for result in results:
        if new := near_points(result[0], near, result[2]) - points:
            chosen.append(result)
            points |= new
    return chosen, len(tried)


# PURPOSE: RUNS THE CHOSEN INPUTS AGAIN AND DROPS ANY WHOSE OUTPUT CHANGED, LISTING THEM WITH THE FIELDS THAT MOVED
def steady(adapter: CobolAdapter, module: IRModule, chosen: list) -> tuple[list, list[dict]]:
    _, again = adapter.execute(module, [inputs for inputs, _, _ in chosen])
    kept, unstable = [], []
    for (inputs, run, got), second in zip(chosen, again):
        moved = sorted(k for k in {*run.output, *second.output} if run.output.get(k) != second.output.get(k))
        if moved or run.rc != second.rc:
            unstable.append({"input": inputs, "fields": moved + ["rc"] * (run.rc != second.rc)})
        else:
            kept.append((inputs, run, got))
    return kept, unstable


# PURPOSE: WHAT A RUN OF THIS PROGRAM SETS: LINKAGE LEAVES, OR THE RECORDS OF THE FILES A BATCH PROGRAM READS
def input_fields(module: IRModule) -> list[Field]:
    return CobolAdapter([]).inputs(module)


# PURPOSE: GOLDEN SUITE FOR ONE PROGRAM: A TEST PER PATH AND PER ON-POINT BOUNDARY VALUE
def characterize(path: Path, root: Path, runner: Runner, copybook_dirs: list[str] = ()) -> dict:
    adapter = CobolAdapter(list(copybook_dirs), root=root, runner=runner)
    module = adapter.parse(Path(path), Path(root))
    program = next(e for e in module.entities if e.kind == "program")
    branches = [e for e in module.entities if e.kind == "branch"]
    fields = adapter.inputs(module)
    pools = {f.key: candidates(f, module) for f in fields}
    bounds = {f.key: boundary_values(f, module) for f in fields}  # RENAME: FIELD TO LITERAL TO CONDITIONS COMPARING THEM
    chosen, count = search(adapter, module, branches, pools, bounds, adapter.is_batch(module))
    chosen, unstable = steady(adapter, module, chosen)
    tests = []
    for n, (inputs, run, got) in enumerate(chosen, 1):
        tests.append({"id": f"{program.name}-{n:02d}", "input": inputs, "output": run.output,
                      "output_digest": output_digest(run.output), "rc": run.rc,
                      "covers": [{"condition": b.id, "outcome": o} for b in branches for o in (True, False)
                                 if (b.id, o) in got],
                      "lines": sorted(line for line, times in run.lines.items() if times),
                      "boundaries": [{"field": f, "value": v, "condition": b}
                                     for f, v, b in sorted(boundary_hits(inputs, bounds, got))]})
    conditions = []
    for b in branches:
        seen = [o for o in (True, False) if any((b.id, o) in got for _, _, got in chosen)]
        conditions.append({"id": b.id, "kind": b.attributes["kind"], "condition": b.attributes["condition"],
                           "provenance": b.provenance.model_dump(exclude_none=True),
                           "decision_line": b.attributes.get("decision_line", b.provenance.line),
                           "true_line": b.attributes["true_line"], "false_line": b.attributes["false_line"],
                           "covered": seen,
                           "tests": [t["id"] for t in tests if any(c["condition"] == b.id for c in t["covers"])]})
    return {"program": program.name,
            "source": {"file": module.path, "digest": digest(Path(path).read_bytes())},
            "runner": runner.describe(),
            "fields": [{"name": f.key, "picture": f.picture, "provenance": f.provenance.model_dump(exclude_none=True),
                        "candidates": pools[f.key]} for f in fields],
            "conditions": conditions, "tests": tests, "runs": count} | ({"unstable": unstable} if unstable else {})


# PURPOSE: RE-RUNS A SUITE'S INPUTS AGAINST THE SOURCE NOW AT ITS PATH; RETURNS THE PROGRAM AND ONE RUN PER TEST
def rerun(suite: dict, root: Path, runner: Runner, copybook_dirs: list[str] = ()) -> tuple[Entity, list[Run]]:
    adapter = CobolAdapter(list(copybook_dirs), root=root, runner=runner)
    module = adapter.parse(Path(root) / suite["source"]["file"], Path(root))
    program = next(e for e in module.entities if e.kind == "program")
    if program.name != suite["program"]:
        raise ValueError(f"{suite['source']['file']} is program {program.name}, the suite is for {suite['program']}")
    return program, adapter.execute(module, [t["input"] for t in suite["tests"]])[1]


# PURPOSE: OUTPUT DIGEST OF A RUN, AS RECORDED IN A SUITE
def output_digest(output: dict[str, str]) -> dict[str, str]:
    return digest(json.dumps(output, sort_keys=True).encode())


# PURPOSE: RE-RUNS A SUITE AGAINST THE SOURCE NOW AT ITS PATH; RETURNS EVERY OUTPUT THAT DIFFERS
def replay(suite: dict, root: Path, runner: Runner, copybook_dirs: list[str] = ()) -> list[dict]:
    differences = []
    for test, run in zip(suite["tests"], rerun(suite, root, runner, copybook_dirs)[1]):
        actual = run.output | {"rc": run.rc}
        for name, expected in (test["output"] | {"rc": test["rc"]}).items():
            if actual.get(name) != expected:
                differences.append({"test": test["id"], "field": name, "expected": expected,
                                    "actual": actual.get(name)})
    return differences
