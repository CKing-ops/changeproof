import itertools
import json
import math
import random
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from changeproof.adapters.base import Entity, IRModule
from changeproof.adapters.cobol import CobolAdapter
from changeproof.adapters.cobol.driver import (Field, boundary_values, branches_about, candidates, linkage_fields,
                                              parse_picture, sides)
from changeproof.adapters.cobol.gnucobol import DockerRunner, LocalRunner, Run, Runner, read_trace
from changeproof.signer import digest

__all__ = ["DockerRunner", "LocalRunner", "Runner", "candidates", "characterize", "input_fields", "linkage_fields", "outcomes",
           "output_digest", "parse_picture", "read_trace", "replay", "rerun"]

MAX_ROUNDS = 6  # RENAME: SEARCH ROUNDS BEFORE GIVING UP ON AN OUTCOME NO INPUT HAS REACHED
JOINT_RUNS = 256  # RENAME: MOST RUNS SPENT ON ONE OUTCOME NO SINGLE-FIELD CHANGE REACHED
JOINT_CHUNK = 64  # RENAME: RUNS PER BUILD WHILE SEARCHING FOR THAT OUTCOME
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


# PURPOSE: (FIELD, VALUE, CONDITION) FOR EACH INPUT SITTING EXACTLY ON A LITERAL A CONDITION THAT RAN COMPARED IT WITH
def boundary_hits(inputs: dict[str, str], bounds: dict[str, dict[str, set[str]]], got: set) -> set[tuple[str, str, str]]:
    ran = {branch for branch, _ in got}
    return {(name, value, branch) for name, value in inputs.items()
            for branch in bounds.get(name, {}).get(value, set()) & ran}


# PURPOSE: (FIELD, VALUE) PAIRS OF A RUN THAT SAT EXACTLY ON A LITERAL A CONDITION THAT RAN COMPARED THE FIELD WITH
def on_point(inputs: dict[str, str], bounds: dict[str, dict[str, set[str]]], got: set) -> set[tuple[str, str]]:
    return {(name, value) for name, value, _ in boundary_hits(inputs, bounds, got)}


@dataclass(frozen=True)
class Space:
    pools: dict[str, list[str]]  # RENAME: FIELD TO THE VALUES TRIED FOR IT
    bounds: dict[str, dict[str, set[str]]]  # RENAME: FIELD TO LITERAL TO CONDITIONS COMPARING THEM
    sides: dict[str, dict[str, list[str]]]  # RENAME: FIELD TO LITERAL TO THE VALUES BELOW, ON AND ABOVE IT
    reads: dict[str, list[str]]  # RENAME: BRANCH TO THE INPUT FIELDS ITS CONDITION READS


# PURPOSE: INPUT SETS THAT RESET TOGETHER EVERY FIELD THE SEED'S CONDITIONS READ: ALL OF THEM, OR A FIXED SAMPLE
def joint(seed: dict[str, str], got: set, space: Space, name: str) -> list[dict[str, str]]:
    keys = sorted({k for branch, _ in got for k in space.reads.get(branch, ()) if len(space.pools[k]) > 1})
    if math.prod(len(space.pools[k]) for k in keys) <= JOINT_RUNS:
        combos = itertools.product(*(space.pools[k] for k in keys))
    else:
        # seeded by the outcome, so the same source always samples the same inputs
        rng = random.Random(name)
        combos = ([rng.choice(space.pools[k]) for k in keys] for _ in range(JOINT_RUNS))
    return [seed | dict(zip(keys, combo)) for combo in combos]


# PURPOSE: (FIELD, VALUE, CONDITION) FOR EACH INPUT BELOW, ON OR ABOVE A LITERAL A CONDITION THAT RAN COMPARED IT WITH
def edge_hits(inputs: dict[str, str], space: Space, got: set) -> set[tuple[str, str, str]]:
    ran = {branch for branch, _ in got}
    return {(name, value, branch) for name, value in inputs.items()
            for literal, near in space.sides.get(name, {}).items() if value in near
            for branch in space.bounds[name][literal] & ran}


# PURPOSE: INPUT SETS THAT MOVE EACH COMPARED FIELD OF A KEPT RUN BELOW, ON AND ABOVE THE LITERAL IT MET
def edges(chosen: list, space: Space) -> list[dict[str, str]]:
    found = []
    for inputs, _, got in chosen:
        ran = {branch for branch, _ in got}
        for name, near in sorted(space.sides.items()):
            for literal, values in sorted(near.items()):
                if space.bounds[name][literal] & ran:
                    found += [inputs | {name: v} for v in values if v in space.pools[name]]
    return found


# PURPOSE: BOUNDARY SEARCH, KEEPING THE FIRST RUN DOWN EACH PATH, ON EACH BOUNDARY POINT AND ON EACH SIDE OF IT
def search(adapter: CobolAdapter, module: IRModule, branches: list[Entity], space: Space,
           batch: bool = False) -> tuple[list, int]:
    pools = space.pools
    bases = [{n: p[0] for n, p in pools.items()}, {n: p[len(p) // 2] for n, p in pools.items()},
             {n: p[-1] for n, p in pools.items()}]
    goal = {(b.id, o) for b in branches for o in (True, False)}
    tried = {}  # RENAME: INPUT SET TO ITS RESULT, NONE WHEN THE RUN WAS DROPPED
    results, covered = [], set()

    # PURPOSE: RUNS THE INPUT SETS NOT RUN BEFORE; RETURNS EVERY KEPT RESULT FOR THE QUEUE, EARLIER ONES INCLUDED
    def run(queue: list[dict[str, str]]) -> list:
        keys = [tuple(sorted(inputs.items())) for inputs in queue]
        fresh = {key: inputs for key, inputs in zip(keys, queue) if key not in tried}
        if fresh:
            for (key, inputs), outcome in zip(fresh.items(), adapter.execute(module, list(fresh.values()))[1]):
                # a batch job's return code is part of its behaviour; a subprogram's driver only fails when the call did
                if outcome.rc == HUNG or (outcome.rc and not batch):
                    tried[key] = None
                else:
                    tried[key] = (inputs, outcome, reached(branches, outcome.lines))
                    results.append(tried[key])
        return [tried[key] for key in dict.fromkeys(keys) if tried[key]]

    queue = bases + [v for b in bases for v in variants(b, pools)]
    for _ in range(MAX_ROUNDS):
        seeds = []
        for inputs, _, got in run(queue):
            if got - covered:
                seeds.append(inputs)
                covered |= got
        if covered >= goal or not seeds:
            break
        queue = [v for s in seeds for v in variants(s, pools)]
    # an outcome no single-field change reached may need several record fields set together
    for branch, outcome in sorted(goal - covered):
        seed = next(((inputs, got) for inputs, _, got in results if any(b == branch for b, _ in got)), None)
        if seed is None or (branch, outcome) in covered:
            continue
        queue = joint(*seed, space, f"{branch}:{outcome}")
        for start in range(0, len(queue), JOINT_CHUNK):
            covered |= set().union(*(got for _, _, got in run(queue[start:start + JOINT_CHUNK])))
            if (branch, outcome) in covered:
                break
    paths = {}  # RENAME: SET OF OUTCOMES A RUN REACHED TO THE FIRST RUN THAT TOOK THAT PATH
    for result in results:
        paths.setdefault(frozenset(result[2]), result)
    chosen = list(paths.values())
    # a run that puts a field exactly on a literal it is compared with catches an off-by-one the paths miss
    points = {p for inputs, _, got in chosen for p in on_point(inputs, space.bounds, got)}
    for result in results:
        if new := on_point(result[0], space.bounds, result[2]) - points:
            chosen.append(result)
            points |= new
    # each path that runs a comparison is tried on both sides of its literal, so a run sitting on the
    # literal (where a charge can multiply by zero) is not that path's only witness
    seen = {h for inputs, _, got in chosen for h in edge_hits(inputs, space, got)}
    for result in run(edges(chosen, space)):
        if new := edge_hits(result[0], space, result[2]) - seen:
            chosen.append(result)
            seen |= new
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
    bounds = {f.key: boundary_values(f, module) for f in fields}
    reads = {}
    for f in fields:
        for b in branches_about(f, module):
            reads.setdefault(b.id, []).append(f.key)
    space = Space(pools, bounds, {f.key: {v: sides(f, v) for v in bounds[f.key]} for f in fields}, reads)
    chosen, count = search(adapter, module, branches, space, adapter.is_batch(module))
    chosen, unstable = steady(adapter, module, chosen)
    tests = []
    for n, (inputs, run, got) in enumerate(chosen, 1):
        tests.append({"id": f"{program.name}-{n:02d}", "input": inputs, "output": run.output,
                      "output_digest": output_digest(run.output), "rc": run.rc,
                      "covers": [{"condition": b.id, "outcome": o} for b in branches for o in (True, False)
                                 if (b.id, o) in got],
                      "lines": sorted(line for line, times in run.lines.items() if times),
                      "boundaries": [{"field": f, "value": v, "condition": b}
                                     for f, v, b in sorted(boundary_hits(inputs, space.bounds, got))]})
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
