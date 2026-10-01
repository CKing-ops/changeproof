import json
from collections import Counter
from pathlib import Path

from changeproof.adapters.base import Entity, IRModule
from changeproof.adapters.cobol import CobolAdapter
from changeproof.adapters.cobol.driver import boundary_values, candidates, linkage_fields, parse_picture
from changeproof.adapters.cobol.gnucobol import DockerRunner, LocalRunner, Run, Runner, read_trace
from changeproof.signer import digest

__all__ = ["DockerRunner", "LocalRunner", "Runner", "candidates", "characterize", "linkage_fields", "outcomes",
           "output_digest", "parse_picture", "read_trace", "replay", "rerun"]

MAX_ROUNDS = 6  # RENAME: SEARCH ROUNDS BEFORE GIVING UP ON AN OUTCOME NO INPUT HAS REACHED


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


# PURPOSE: (FIELD, VALUE) PAIRS OF A RUN THAT SAT EXACTLY ON A LITERAL A CONDITION THAT RAN COMPARED THE FIELD WITH
def on_point(inputs: dict[str, str], bounds: dict[str, dict[str, set[str]]], got: set) -> set[tuple[str, str]]:
    ran = {branch for branch, _ in got}
    return {(name, value) for name, value in inputs.items() if bounds.get(name, {}).get(value, set()) & ran}


# PURPOSE: BOUNDARY SEARCH, KEEPING THE FIRST RUN DOWN EACH PATH AND THE FIRST RUN ON EACH BOUNDARY POINT
def search(adapter: CobolAdapter, module: IRModule, branches: list[Entity], pools: dict[str, list[str]],
           bounds: dict[str, dict[str, set[str]]]) -> tuple[list, int]:
    bases = [{n: p[0] for n, p in pools.items()}, {n: p[len(p) // 2] for n, p in pools.items()},
             {n: p[-1] for n, p in pools.items()}]
    goal = {(b.id, o) for b in branches for o in (True, False)}
    tried, results, covered = set(), [], set()
    batch = bases + [v for b in bases for v in variants(b, pools)]
    for _ in range(MAX_ROUNDS):
        fresh = []  # RENAME: INPUT SETS NOT RUN BEFORE
        for inputs in batch:
            if (key := tuple(sorted(inputs.items()))) not in tried:
                tried.add(key)
                fresh.append(inputs)
        batch = fresh
        if not batch:
            break
        _, runs = adapter.execute(module, batch)
        seeds = []
        for inputs, run in zip(batch, runs):
            if run.rc:
                continue
            got = reached(branches, run.lines)
            if got - covered:
                seeds.append(inputs)
                covered |= got
            results.append((inputs, run, got))
        if covered >= goal:
            break
        batch = [v for s in seeds for v in variants(s, pools)]
    paths = {}  # RENAME: SET OF OUTCOMES A RUN REACHED TO THE FIRST RUN THAT TOOK THAT PATH
    for result in results:
        paths.setdefault(frozenset(result[2]), result)
    chosen = list(paths.values())
    # a run that puts a field exactly on a literal it is compared with catches an off-by-one the paths miss
    points = {p for inputs, _, got in chosen for p in on_point(inputs, bounds, got)}
    for result in results:
        if new := on_point(result[0], bounds, result[2]) - points:
            chosen.append(result)
            points |= new
    return chosen, len(tried)


# PURPOSE: GOLDEN SUITE FOR ONE LINKAGE SUBPROGRAM: A TEST PER PATH AND PER ON-POINT BOUNDARY VALUE
def characterize(path: Path, root: Path, runner: Runner, copybook_dirs: list[str] = ()) -> dict:
    adapter = CobolAdapter(list(copybook_dirs), root=root, runner=runner)
    module = adapter.parse(Path(path), Path(root))
    program = next(e for e in module.entities if e.kind == "program")
    branches = [e for e in module.entities if e.kind == "branch"]
    fields = [f for f in linkage_fields(module) if f.picture]
    pools = {f.name: candidates(f, module) for f in fields}
    chosen, count = search(adapter, module, branches, pools, {f.name: boundary_values(f, module) for f in fields})
    tests = []
    for n, (inputs, run, got) in enumerate(chosen, 1):
        tests.append({"id": f"{program.name}-{n:02d}", "input": inputs, "output": run.output,
                      "output_digest": output_digest(run.output), "rc": run.rc,
                      "covers": [{"condition": b.id, "outcome": o} for b in branches for o in (True, False)
                                 if (b.id, o) in got]})
    conditions = []
    for b in branches:
        seen = [o for o in (True, False) if any((b.id, o) in got for _, _, got in chosen)]
        conditions.append({"id": b.id, "kind": b.attributes["kind"], "condition": b.attributes["condition"],
                           "provenance": b.provenance.model_dump(exclude_none=True),
                           "true_line": b.attributes["true_line"], "false_line": b.attributes["false_line"],
                           "covered": seen,
                           "tests": [t["id"] for t in tests if any(c["condition"] == b.id for c in t["covers"])]})
    return {"program": program.name,
            "source": {"file": module.path, "digest": digest(Path(path).read_bytes())},
            "runner": runner.describe(),
            "fields": [{"name": f.name, "picture": f.picture, "provenance": f.provenance.model_dump(exclude_none=True),
                        "candidates": pools[f.name]} for f in fields],
            "conditions": conditions, "tests": tests, "runs": count}


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
