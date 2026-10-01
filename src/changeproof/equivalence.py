"""Behavioral-equivalence evidence (ROADMAP Week 9), as a behavioral-equivalence predicate v0.1.

Characterization tests are built from each program at the base of a change and replayed on the same
program at the head. By default only programs outside the change's impact set are tested: what the
change did not touch must behave as before. A program that cannot be tested is listed with why, and
makes the verdict inconclusive rather than passing it.
"""

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from changeproof import __version__
from changeproof.adapters.base import Entity
from changeproof.adapters.cobol import CobolAdapter
from changeproof.adapters.cobol.parse import CobolSyntaxError
from changeproof.change.git import checkout_tree, empty_tree
from changeproof.change.record import PROGRAM_SUFFIXES
from changeproof.characterize import LocalRunner, Runner, characterize, output_digest, rerun
from changeproof.impact import ImpactRun, run_impact
from changeproof.impact.run import CONFIG_NAME, files_with
from changeproof.predicates import PREDICATE_TYPES, statement, validate_predicate
from changeproof.signer import digest

SCOPES = ("outside-impact-set", "full-suite")
NO_STUBS = "not a linkage subprogram (no PROCEDURE DIVISION USING); programs that read files, Db2 or CICS need stubs, which are planned"


@dataclass(frozen=True)
class EquivalenceRun:
    predicate: dict
    impact: ImpactRun
    in_impact_set: list[str]  # program names the change touches or reaches


# PURPOSE: THE IN-TOTO SUBJECT FOR EVIDENCE ABOUT A CHANGE: THE REPOSITORY AT ITS HEAD COMMIT
def change_subject(predicate: dict) -> dict:
    return {"name": predicate["change"]["repository"], "digest": {"gitCommit": predicate["change"]["head"]}}


# PURPOSE: DIGEST OF THE IMPACT STATEMENT, AS CANONICAL JSON, THAT DEFINES WHAT AN EQUIVALENCE RUN LEAVES OUT
def impact_statement_digest(impact_predicate: dict) -> dict:
    found = statement([change_subject(impact_predicate)], PREDICATE_TYPES["impact"], impact_predicate)
    return digest(json.dumps(found, sort_keys=True, separators=(",", ":")).encode())


# PURPOSE: PROGRAMS THAT OWN A CHANGED OR IMPACTED ENTITY
def impact_programs(predicate: dict, programs: set[str]) -> set[str]:
    owners = {e["id"].partition(":")[2].split(".")[0].split("#")[0] for e in predicate["changed"] + predicate["impacted"]}
    return owners & programs


# PURPOSE: A KEPT BASELINE SUITE FOR THIS SOURCE AND RUNNER, ELSE A NEW ONE, KEPT WHEN A FOLDER IS GIVEN
def baseline(path: Path, root: Path, runner: Runner, copybook_dirs: list[str], folder: Path | None) -> dict:
    kept = folder / f"{path.stem}-{digest(path.read_bytes())['sha-384'][:16]}.json" if folder else None
    if kept and kept.is_file():
        suite = json.loads(kept.read_text(encoding="utf-8"))
        if suite["runner"] == runner.describe():
            return suite
    suite = characterize(path, root, runner, copybook_dirs)
    if kept:
        kept.write_text(json.dumps(suite, indent=2) + "\n", encoding="utf-8")
    return suite


# PURPOSE: AN ENTITY AS THE PREDICATE'S ENTITYREF
def entity_ref(entity: Entity) -> dict:
    return {"id": entity.id, "kind": entity.kind, "name": entity.name,
            "provenance": entity.provenance.model_dump(mode="json")}


# PURPOSE: REPLAYS ONE PROGRAM'S BASELINE AT THE HEAD; ONE PREDICATE TEST ENTRY PER CHARACTERIZATION TEST
def compare(suite: dict, after: Path, runner: Runner, copybook_dirs: list[str], target: dict) -> list[dict]:
    try:
        _, runs = rerun(suite, after, runner, copybook_dirs)
    except (RuntimeError, ValueError) as exc:
        failed = digest(str(exc).encode())
        return [{"id": t["id"], "target": target, "result": "error", "baseline_output": t["output_digest"],
                 "candidate_output": failed} for t in suite["tests"]]
    return [{"id": t["id"], "target": target,
             "result": "same" if (r.output, r.rc) == (t["output"], t["rc"]) else "different",
             "baseline_output": t["output_digest"], "candidate_output": output_digest(r.output)}
            for t, r in zip(suite["tests"], runs)]


# PURPOSE: RUNNER, IMAGE AND NETWORK AS THE PREDICATE RECORDS THEM
def environment(runner: Runner) -> dict:
    found = runner.describe()
    env = {"runner": f"{found['kind']}: {found['cobc']}"}
    if "image_id" in found:
        env |= {"image": {"sha-256": found["image_id"].removeprefix("sha256:")}, "network": "disabled"}
    return env


# PURPOSE: THE BEHAVIORAL-EQUIVALENCE PREDICATE FOR A COMMIT OR RANGE, VALIDATED AGAINST ITS SCHEMA
def equivalence(root: Path, revisions: str, copybook_dirs: list[str] = (), config_path: str = CONFIG_NAME,
                scope: str = "outside-impact-set", runner: Runner | None = None,
                baselines: Path | None = None) -> EquivalenceRun:
    if scope not in SCOPES:
        raise ValueError(f"unknown scope '{scope}' ({', '.join(SCOPES)})")
    run = run_impact(Path(root), revisions, list(copybook_dirs), config_path)
    return equivalence_of(run, root, copybook_dirs, scope, runner, baselines)


# PURPOSE: THE EQUIVALENCE RUN FOR A CHANGE WHOSE IMPACT HAS ALREADY BEEN ANALYSED
def equivalence_of(run: ImpactRun, root: Path, copybook_dirs: list[str] = (), scope: str = "outside-impact-set",
                   runner: Runner | None = None, baselines: Path | None = None) -> EquivalenceRun:
    root, copybook_dirs, runner = Path(root), list(copybook_dirs), runner or LocalRunner()
    change = run.predicate["change"]
    adapter = CobolAdapter(copybook_dirs)
    tests, untested = [], []
    with tempfile.TemporaryDirectory() as scratch:
        after = checkout_tree(root, change["head"], Path(scratch) / "after")
        before = None if change["base"] == empty_tree(root) else checkout_tree(root, change["base"], Path(scratch) / "before")
        programs = {}  # RENAME: HEAD PATH TO ITS PROGRAM ENTITY
        for path in files_with(after, PROGRAM_SUFFIXES, copybook_dirs):
            try:
                programs[path] = next(e for e in adapter.parse(after / path, after).entities if e.kind == "program")
            except CobolSyntaxError as exc:
                untested.append({"provenance": {"file": path, "line": 1},
                                 "reason": f"does not parse at the head: {exc.errors[0][1] if exc.errors else exc}"})
        in_set = impact_programs(run.predicate, {p.name for p in programs.values()})
        for path, program in programs.items():
            if scope == "outside-impact-set" and program.name in in_set:
                continue
            gap = {"program": program.name, "provenance": program.provenance.model_dump(mode="json")}
            if "using" not in program.attributes:
                untested.append(gap | {"reason": NO_STUBS})
                continue
            if before is None or not (before / path).is_file():
                untested.append(gap | {"reason": "not in the base, so there is nothing to compare with"})
                continue
            try:
                suite = baseline(before / path, before, runner, copybook_dirs, Path(baselines) if baselines else None)
            except (ValueError, CobolSyntaxError, RuntimeError) as exc:
                untested.append(gap | {"reason": f"no baseline: {exc}"})
                continue
            tests += compare(suite, after, runner, copybook_dirs, entity_ref(program))
    summary = {"total": len(tests)} | {k: sum(t["result"] == k for t in tests) for k in ("same", "different", "error")}
    if summary["different"]:
        verdict = "not-equivalent"
    elif summary["error"] or untested or not tests:
        verdict = "inconclusive"
    else:
        verdict = "equivalent"
    predicate = {
        "change": change,
        "impact_statement": impact_statement_digest(run.predicate),
        "scope": scope,
        "tests": tests,
        "untested": untested,
        "summary": summary,
        "verdict": verdict,
        "environment": environment(runner),
        "engine": {"name": "changeproof", "version": __version__,
                   "adapters": [{"language": "cobol", "version": __version__, "parser": "antlr4-cobol85"}]},
    }
    validate_predicate(PREDICATE_TYPES["behavioral-equivalence"], predicate)
    return EquivalenceRun(predicate, run, sorted(in_set))
