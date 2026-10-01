"""Policy gate (ROADMAP Week 7): the rules named in `policy:` run as OPA/Rego over facts the engine read.

The engine builds the policy input from the impact run (crypto calls that changed, who approved,
which components changed), every fact with its provenance. OPA evaluates the bundled Rego offline,
as a separate process like git. The equivalence rule also needs characterization runs (Week 9); when
they cannot run, the rule is reported `not-evaluated`, never passed.
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from changeproof.adapters.base import ChangeKind
from changeproof.equivalence import EquivalenceRun, equivalence_of
from changeproof.impact import ImpactRun, run_impact

POLICY_DIR = Path(str(files("changeproof").joinpath("policies")))
EQUIVALENCE_RULE = "equivalence-required-outside-impact-set"  # RENAME: THE RULE THAT NEEDS CHARACTERIZATION RUNS
CRYPTO_FIELDS = ("algorithm", "key_bits", "quantum_vulnerable")


@dataclass(frozen=True)
class GateResult:
    run: ImpactRun
    input: dict  # the facts the rules saw
    decision: dict  # per-rule outcome, overall ok, OPA version


# PURPOSE: RULE ID TO "REGO" FOR EACH BUNDLED POLICY
def known_rules() -> dict[str, str]:
    return {p.stem.replace("_", "-"): "rego" for p in POLICY_DIR.glob("*.rego")}


# PURPOSE: THE OPA EXECUTABLE: $CHANGEPROOF_OPA IF SET, ELSE OPA ON THE PATH
def opa_path() -> str | None:
    return os.environ.get("CHANGEPROOF_OPA") or shutil.which("opa")


# PURPOSE: CHANGED CRYPTO CALLS WITH THEIR ALGORITHM BEFORE AND AFTER
def crypto_facts(run: ImpactRun) -> list[dict]:
    found = []
    for c in run.what.entities:
        if c.entity.kind != "crypto-call" or c.change == ChangeKind.REMOVED:
            continue
        before = c.previous.attributes if c.change == ChangeKind.MODIFIED and c.previous else None
        found.append({"id": c.entity.id, "service": c.entity.attributes["service"], "change": c.change.value,
                      **{k: c.entity.attributes.get(k) for k in CRYPTO_FIELDS},
                      "algorithm_from": c.entity.attributes.get("algorithm_from", []),
                      "previous": {k: before.get(k) for k in CRYPTO_FIELDS} if before else None,
                      "provenance": c.entity.provenance.model_dump(mode="json", exclude_none=True)})
    return found


# PURPOSE: CONFIGURED COMPONENTS, EACH MARKED CHANGED WHEN A CHANGED FILE LIES UNDER ITS PATH
def component_facts(run: ImpactRun) -> list[dict]:
    if run.config is None:
        return []
    touched = {c.entity.provenance.file for c in run.what.entities} | set(run.what.not_analyzed)
    return [{"id": c.id, "criticality": c.criticality.value,
             "changed": any(f == c.path or f.startswith(c.path.rstrip("/") + "/") for f in touched),
             "provenance": {"file": run.config_path, "line": run.component_at[c.id]}}
            for c in run.config.components]


# PURPOSE: THE POLICY INPUT: EVERY FACT A RULE MAY READ, EACH WITH WHERE IT CAME FROM
def policy_input(run: ImpactRun) -> dict:
    people = run.predicate["who"]
    return {
        "change": run.predicate["change"],
        "crypto": crypto_facts(run),
        "components": component_facts(run),
        "approvers": [{"id": p["id"], "source": p["source"]} for p in people if p["role"] == "approver"],
        "implementers": [{"id": p["id"], "source": p["source"]} for p in people if p["role"] == "author"],
    }


# PURPOSE: WHAT THE EQUIVALENCE RULE READS: TESTS THAT DIFFERED OR FAILED, AND PROGRAMS WITH NO TESTS
def equivalence_facts(found: EquivalenceRun) -> dict:
    p = found.predicate
    rows = {result: [{"program": t["target"]["name"], "test": t["id"], "provenance": t["target"]["provenance"]}
                     for t in p["tests"] if t["result"] == result] for result in ("different", "error")}
    return {"verdict": p["verdict"], "scope": p["scope"], "differing": rows["different"], "errors": rows["error"],
            "untested": p["untested"]}


# PURPOSE: EVALUATES EVERY BUNDLED RULE PACKAGE WITH OPA, OFFLINE; RETURNS (PACKAGE OUTCOMES, OPA VERSION)
def evaluate(facts: dict) -> tuple[dict, str]:
    opa = opa_path()
    if not opa or not Path(opa).is_file():
        raise FileNotFoundError(f"OPA not found ({opa or 'not on PATH'}); install it or set CHANGEPROOF_OPA")
    version = subprocess.run([opa, "version"], capture_output=True, text=True, check=True).stdout
    proc = subprocess.run([opa, "eval", "--format", "json", "--stdin-input", "--data", str(POLICY_DIR),
                           "data.changeproof.rules"], input=json.dumps(facts), capture_output=True, text=True,
                          check=True)
    value = json.loads(proc.stdout)["result"][0]["expressions"][0]["value"]
    return value, version.splitlines()[0].removeprefix("Version:").strip()


# PURPOSE: RUNS THE IMPACT ANALYSIS AND THE CONFIGURED RULES FOR A COMMIT OR RANGE
def gate(root: Path, revisions: str, copybook_dirs: list[str] = (), config_path: str = "changeproof.yaml") -> GateResult:
    run = run_impact(root, revisions, copybook_dirs, config_path)
    named = [r.rule for r in run.config.policy] if run.config else []
    known = known_rules()
    if unknown := [r for r in named if r not in known]:
        raise ValueError(f"policy rule '{unknown[0]}' is not known ({', '.join(sorted(known))})")
    facts = policy_input(run)
    skipped = {}  # RENAME: RULE ID TO WHY IT COULD NOT BE EVALUATED
    if EQUIVALENCE_RULE in named:
        try:
            facts["equivalence"] = equivalence_facts(equivalence_of(run, root, copybook_dirs))
        except RuntimeError as exc:  # no GnuCOBOL: the rule has no evidence, so it is not passed
            skipped[EQUIVALENCE_RULE] = str(exc)
    outcomes, version = evaluate(facts)
    rules = []
    for rule in named:
        if rule in skipped:
            rules.append({"rule": rule, "status": "not-evaluated", "reason": skipped[rule], "deny": [], "warn": []})
            continue
        found = outcomes[rule.replace("-", "_")]
        deny = sorted(found.get("deny", []), key=json.dumps)
        # no difference found but some code went untested: not a failure, and not a pass either
        unproven = rule == EQUIVALENCE_RULE and facts["equivalence"]["verdict"] == "inconclusive"
        rules.append({"rule": rule, "status": "fail" if deny else "inconclusive" if unproven else "pass", "deny": deny,
                      "warn": sorted(found.get("warn", []), key=json.dumps)})
    decision = {"ok": all(r["status"] != "fail" for r in rules), "opa": version, "rules": rules}
    return GateResult(run, facts, decision)
