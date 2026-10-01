"""Policy gate (ROADMAP Week 7): the rules named in `policy:` run as OPA/Rego over facts the engine read.

The engine builds the policy input from the impact run (crypto calls that changed, who approved,
which components changed), every fact with its provenance. OPA evaluates the bundled Rego offline,
as a separate process like git. A rule whose evidence does not exist yet is reported
`not-evaluated`, never passed.
"""

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path

from changeproof.adapters.base import ChangeKind
from changeproof.impact import ImpactRun, run_impact

POLICY_DIR = Path(str(files("changeproof").joinpath("policies")))
PLANNED_RULES = {  # RENAME: RULES NAMED IN CONFIGS WHOSE EVIDENCE IS NOT BUILT YET, WITH WHY
    "equivalence-required-outside-impact-set": "behavioral-equivalence evidence is planned (ROADMAP Weeks 8-9)",
}
CRYPTO_FIELDS = ("algorithm", "key_bits", "quantum_vulnerable")


@dataclass(frozen=True)
class GateResult:
    run: ImpactRun
    input: dict  # the facts the rules saw
    decision: dict  # per-rule outcome, overall ok, OPA version


# PURPOSE: RULE ID TO "REGO" FOR EACH BUNDLED POLICY AND "PLANNED" FOR RULES WITHOUT EVIDENCE YET
def known_rules() -> dict[str, str]:
    found = {p.stem.replace("_", "-"): "rego" for p in POLICY_DIR.glob("*.rego")}
    return found | {rule: "planned" for rule in PLANNED_RULES}


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
    facts = policy_input(run)
    outcomes, version = evaluate(facts)
    rules = []
    known = known_rules()
    for rule in (r.rule for r in run.config.policy) if run.config else ():
        if rule not in known:
            raise ValueError(f"policy rule '{rule}' is not known ({', '.join(sorted(known))})")
        if rule in PLANNED_RULES:
            rules.append({"rule": rule, "status": "not-evaluated", "reason": PLANNED_RULES[rule], "deny": [], "warn": []})
            continue
        found = outcomes[rule.replace("-", "_")]
        deny = sorted(found.get("deny", []), key=json.dumps)
        rules.append({"rule": rule, "status": "fail" if deny else "pass", "deny": deny,
                      "warn": sorted(found.get("warn", []), key=json.dumps)})
    decision = {"ok": all(r["status"] != "fail" for r in rules), "opa": version, "rules": rules}
    return GateResult(run, facts, decision)
