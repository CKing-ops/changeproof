"""OSCAL 1.1.2 assessment-results export of a gate run (ROADMAP Week 7).

The engine reports evidence and the outcome of its own policy rules. It makes no determination
about a framework control: controls are listed as reviewed, and each finding targets a policy rule.
"""

import json
import re
from datetime import UTC, datetime
from functools import cache
from importlib.resources import files

import jsonschema
from jsonschema import validators

from changeproof import __version__
from changeproof.frameworks import controls_for
from changeproof.gate import GateResult
from changeproof.markets import MARKETS
from changeproof.signer import name_uuid

OSCAL_VERSION = "1.1.2"
SCHEMA_FILE = f"oscal_complete_schema-{OSCAL_VERSION}.json"
NS = "urn:changeproof:oscal"
# Python's re has no \p classes; these are the two the schema uses, as close as re allows
UNICODE_CLASSES = {r"\p{L}": r"[^\W\d_]", r"\p{N}": r"\d"}
RULE_EVIDENCE = {  # RENAME: POLICY RULE TO THE OBSERVATION GROUPS ITS FINDING CITES
    "no-new-quantum-vulnerable-crypto": ("crypto", "impact"),
    "high-criticality-needs-two-approvers": ("approvals", "components"),
}


# PURPOSE: THE JSON SCHEMA "PATTERN" KEYWORD, WITH THE SCHEMA'S UNICODE CLASSES TRANSLATED FOR RE
def unicode_pattern(validator, pattern, instance, schema):
    if not validator.is_type(instance, "string"):
        return
    for name, translated in UNICODE_CLASSES.items():
        pattern = pattern.replace(name, translated)
    if not re.search(pattern, instance):
        yield jsonschema.ValidationError(f"{instance!r} does not match {pattern!r}")


# PURPOSE: VALIDATOR FOR THE BUNDLED NIST OSCAL COMPLETE SCHEMA
@cache
def oscal_validator() -> jsonschema.Draft7Validator:
    schema = json.loads(files("changeproof.oscal").joinpath(SCHEMA_FILE).read_text(encoding="utf-8"))
    checker = validators.extend(jsonschema.Draft7Validator, {"pattern": unicode_pattern})
    return checker(schema, format_checker=jsonschema.Draft7Validator.FORMAT_CHECKER)


# PURPOSE: RAISES THE FIRST SCHEMA ERROR IN AN OSCAL DOCUMENT
def validate_oscal(doc: dict) -> None:
    if error := jsonschema.exceptions.best_match(oscal_validator().iter_errors(doc)):
        raise error


# PURPOSE: OSCAL TOKEN FOR A FRAMEWORK CONTROL, E.G. SOC2_CC8.1
def control_token(framework: str, control: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", f"{framework}_{control}").strip("-")


# PURPOSE: FILE:LINE, OR FILE:LINE-END, FOR A PROVENANCE DICT
def where(provenance: dict) -> str:
    end = provenance.get("end_line")
    return f"{provenance['file']}:{provenance['line']}" + (f"-{end}" if end and end != provenance["line"] else "")


# PURPOSE: A COPY WITHOUT EMPTY LISTS, WHICH OSCAL REJECTS (EVERY ARRAY NEEDS AN ITEM)
def compact(item: dict) -> dict:
    return {k: v for k, v in item.items() if v != []}


# PURPOSE: PROVENANCE PROPS FOR A LIST OF PROVENANCE DICTS
def provenance_props(items: list[dict]) -> list[dict]:
    return [{"name": "provenance", "ns": NS, "value": where(p)} for p in items]


# PURPOSE: OBSERVATIONS, GROUPED BY WHAT THEY RECORD, FOR THE FACTS THE RULES SAW
def observations(result: GateResult, key: str, at: str) -> dict[str, list[dict]]:
    facts, predicate = result.input, result.run.predicate
    tiers = [i["confidence"] for i in predicate["impacted"]]
    groups = {"impact": [{
        "uuid": name_uuid(f"{key}:observation:impact"), "title": "Impact of the change",
        "description": f"{len(predicate['changed'])} entities changed and {len(tiers)} impacted "
                       f"({tiers.count('definite')} definite, {tiers.count('probable')} probable, "
                       f"{tiers.count('possible')} possible); {len(predicate['unresolved'])} gaps reported.",
        "methods": ["TEST"], "collected": at,
        "props": provenance_props([c["provenance"] for c in predicate["changed"]]),
    }]}
    groups["crypto"] = [{
        "uuid": name_uuid(f"{key}:observation:{c['id']}"), "title": f"Crypto call {c['service']} ({c['change']})",
        "description": f"{c['service']} uses {c['algorithm'] or 'an algorithm that could not be read'}"
                       + (f" with a {c['key_bits']}-bit key" if c["key_bits"] else "")
                       + {True: "; quantum-vulnerable.", False: "; not quantum-vulnerable.", None: "."}[c["quantum_vulnerable"]],
        "methods": ["EXAMINE"], "collected": at, "props": provenance_props([c["provenance"]]),
    } for c in facts["crypto"]]
    people = facts["approvers"] + facts["implementers"]
    groups["approvals"] = [{
        "uuid": name_uuid(f"{key}:observation:approvals"), "title": "Approvals",
        "description": f"{len(facts['approvers'])} approvers and {len(facts['implementers'])} implementers recorded "
                       "in the commits; requester, implementer and approver are kept apart.",
        "methods": ["EXAMINE"], "collected": at,
        "props": [{"name": "source", "ns": NS, "value": f"{p['id']}: {p['source']}"} for p in people],
    }]
    groups["components"] = [{
        "uuid": name_uuid(f"{key}:observation:components"), "title": "Components changed",
        "description": ", ".join(f"{c['id']} ({c['criticality']}, {'changed' if c['changed'] else 'unchanged'})"
                                 for c in facts["components"]) or "No components are configured.",
        "methods": ["EXAMINE"], "collected": at,
        "props": provenance_props([c["provenance"] for c in facts["components"]]),
    }]
    return {name: [compact(o) for o in group] for name, group in groups.items()}


# PURPOSE: ONE FINDING PER EVALUATED POLICY RULE, CITING THE OBSERVATIONS IT RESTS ON
def findings(result: GateResult, key: str, groups: dict[str, list[dict]]) -> list[dict]:
    found = []
    for rule in result.decision["rules"]:
        if rule["status"] == "not-evaluated":
            continue
        messages = [d["message"] for d in rule["deny"]] + [f"warning: {w['message']}" for w in rule["warn"]]
        cited = [o for g in RULE_EVIDENCE.get(rule["rule"], ()) for o in groups[g]]
        found.append(compact({
            "uuid": name_uuid(f"{key}:finding:{rule['rule']}"), "title": f"Policy rule {rule['rule']}",
            "description": "; ".join(messages) or "The rule holds for this change.",
            "props": provenance_props([d["provenance"] for d in rule["deny"] + rule["warn"]]),
            "target": {"type": "objective-id", "target-id": rule["rule"],
                       "status": {"state": "satisfied" if rule["status"] == "pass" else "not-satisfied"}},
            "related-observations": [{"observation-uuid": o["uuid"]} for o in cited],
        }))
    return found


# PURPOSE: OSCAL ASSESSMENT-RESULTS DOCUMENT FOR A GATE RUN; SAME INPUTS AND TIME GIVE THE SAME DOCUMENT
def assessment_results(result: GateResult, at: datetime) -> dict:
    change, config = result.run.predicate["change"], result.run.config
    key = f"{change['repository']}:{change['base']}..{change['head']}"
    stamp = at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    frameworks = (config.frameworks or MARKETS[config.market].frameworks) if config else ()
    controls = list(dict.fromkeys(control_token(c.framework, c.id) for f in frameworks for c in controls_for(f)))
    groups = observations(result, key, stamp)
    plan = name_uuid(f"{key}:plan")
    skipped = [f"{r['rule']}: {r['reason']}" for r in result.decision["rules"] if r["status"] == "not-evaluated"]
    run = compact({
        "uuid": name_uuid(f"{key}:result"), "title": "changeproof policy gate",
        "description": f"Impact and policy evidence for {change['repository']} {change['base']}..{change['head']}, "
                       f"rules evaluated by OPA {result.decision['opa']}. Findings target policy rules; no "
                       "determination is made about any framework control.",
        "start": stamp, "end": stamp,
        "reviewed-controls": {"control-selections": [
            {"include-controls": [{"control-id": c} for c in controls]} if controls else {"include-all": {}}]},
        "observations": [o for g in groups.values() for o in g],
        "findings": findings(result, key, groups),
        **({"remarks": "Not evaluated: " + "; ".join(skipped)} if skipped else {}),
    })
    return {"assessment-results": {
        "uuid": name_uuid(f"{key}:assessment-results"),
        "metadata": {"title": f"changeproof evidence for {change['repository']} {change['head'][:12]}",
                     "last-modified": stamp, "version": __version__, "oscal-version": OSCAL_VERSION},
        "import-ap": {"href": f"#{plan}"},
        "results": [run],
        "back-matter": {"resources": [{
            "uuid": plan, "title": "changeproof policy gate",
            "description": "Rules named in the policy section of changeproof.yaml: "
                           + ", ".join(r["rule"] for r in result.decision["rules"]) + "."}]},
    }}
