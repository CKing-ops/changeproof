"""Assessor evidence pack for a release (ROADMAP Week 12).

For each commit in the release the pack holds four signed attestations: impact, policy decision,
behavioral equivalence outside the impact set, and the full suite (which shows what the change
altered inside the impact set, Week 13). The PDF report and the OSCAL assessment results are built from those
attestations only, so anyone holding the pack and the public keys can verify every signature and
rebuild both, byte for byte, with no repository and no network. A signed pack statement lists the
attestations, states the crypto profile, and carries the digest of every file in the pack.
"""

import base64
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from changeproof.change.git import commits_in
from changeproof.characterize import Runner
from changeproof.equivalence import change_subject, equivalence_of, impact_programs, impact_statement_digest
from changeproof.frameworks import FRAMEWORK_LABELS, NOT_MAPPED, PLANNED, controls_for
from changeproof.gate import gate, policy_decision
from changeproof.impact.run import CONFIG_NAME
from changeproof.oscal import assessment_results_of, validate_oscal
from changeproof.pack.pdf import render
from changeproof.predicates import PREDICATE_TYPES, statement, validate_predicate
from changeproof.signer import Policy, PrivateKey, PublicKey, Verification, digest, sign_envelope, verify_envelope

PACK_FILE = "pack.dsse.json"
REPORT = "report.pdf"
KINDS = {  # RENAME: ATTESTATION KIND KEPT FOR EACH COMMIT TO ITS PREDICATE TYPE
    "impact": PREDICATE_TYPES["impact"],
    "policy-decision": PREDICATE_TYPES["policy-decision"],
    "behavioral-equivalence": PREDICATE_TYPES["behavioral-equivalence"],
    "full-suite": PREDICATE_TYPES["behavioral-equivalence"],
}
LISTED = 40  # RENAME: CHANGED OR IMPACTED ENTITIES THE REPORT LISTS PER CHANGE; THE ATTESTATION HOLDS ALL


@dataclass(frozen=True)
class PackCheck:
    ok: bool
    problems: list[str]
    rebuilt: dict[str, bytes]  # pack path to the bytes rebuilt from the attestations


# PURPOSE: CANONICAL JSON BYTES, THE FORM ENVELOPES SIGN
def canonical(data: dict) -> bytes:
    return json.dumps(data, sort_keys=True, separators=(",", ":")).encode()


# PURPOSE: THE STATEMENT INSIDE A DSSE ENVELOPE
def payload_of(envelope: dict) -> dict:
    return json.loads(base64.b64decode(envelope["payload"]))


# PURPOSE: FILE NAME STEM FOR THE NTH COMMIT OF A RELEASE
def stem(n: int, sha: str) -> str:
    return f"{n:02d}-{sha[:12]}"


# PURPOSE: WHY THE KEYS DO NOT FIT THE CONFIG'S CRYPTO SECTION, OR NONE
def key_mismatch(crypto, keys: list[PrivateKey], release_key: PrivateKey | None) -> str | None:
    if sorted(k.alg for k in keys) != sorted(crypto.signing):
        return (f"crypto.signing is {', '.join(crypto.signing)} but the keys given are "
                f"{', '.join(k.alg for k in keys)}; sign with exactly the configured algorithms")
    if release_key and release_key.alg != crypto.release_signing:
        return f"crypto.release_signing is {crypto.release_signing} but the release key is {release_key.alg}"
    return None


# PURPOSE: BUILDS THE PACK FOR A RELEASE INTO A NEW FOLDER, SIGNING EVERY ATTESTATION AND THE PACK STATEMENT
def build_pack(root: Path, revisions: str, out: Path, keys: list[PrivateKey], release: str | None = None,
               copybook_dirs: list[str] = (), config_path: str = CONFIG_NAME, at: datetime | None = None,
               runner: Runner | None = None, release_key: PrivateKey | None = None) -> dict:
    root, out, at = Path(root), Path(out), at or datetime.now(UTC)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"{out} is not empty")
    (out / "attestations").mkdir(parents=True, exist_ok=True)
    listed, changes = [], []
    for n, sha in enumerate(commits_in(root, revisions), 1):
        result = gate(root, sha, copybook_dirs, config_path)
        config, engine = result.run.config, result.run.predicate["engine"]
        if config and (problem := key_mismatch(config.crypto, keys, release_key)):
            raise ValueError(f"{sha[:12]}: {problem}")
        tested = result.equivalence or equivalence_of(result.run, root, copybook_dirs, runner=runner)
        full = equivalence_of(result.run, root, copybook_dirs, "full-suite", runner)
        changes.append(result.run.predicate["change"])
        bodies = dict(zip(KINDS, (result.run.predicate, policy_decision(result, at), tested.predicate, full.predicate)))
        for kind, body in bodies.items():
            found = statement([change_subject(body)], KINDS[kind], body)
            path = f"attestations/{stem(n, sha)}-{kind}.dsse.json"
            (out / path).write_text(json.dumps(sign_envelope(found, keys, at), indent=2) + "\n", encoding="utf-8")
            listed.append({"path": path, "predicate_type": KINDS[kind], "commit": sha,
                           "payload": digest(canonical(found))})
    signers = [*keys, *([release_key] if release_key else [])]
    crypto = {"profile": config.crypto.profile, "signing": list(config.crypto.signing),
              "release_signing": config.crypto.release_signing, "hash": config.crypto.hash} if config else {"profile": None}
    predicate = {
        "release": release or revisions,
        "change": changes[0] | {"head": changes[-1]["head"]},
        "crypto": crypto | {"signed_with": [{"alg": k.alg, "keyid": k.keyid} for k in signers]},
        "attestations": listed,
        "generated_at": at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "engine": engine,
    }
    validate_predicate(PREDICATE_TYPES["evidence-pack"], predicate)
    for path, data in derived(predicate, evidence_of(out, predicate)).items():
        (out / path).parent.mkdir(parents=True, exist_ok=True)
        (out / path).write_bytes(data)
    subjects = [{"name": p.relative_to(out).as_posix(), "digest": digest(p.read_bytes())}
                for p in sorted(out.rglob("*")) if p.is_file()]
    signed = sign_envelope(statement(subjects, PREDICATE_TYPES["evidence-pack"], predicate), signers, at)
    (out / PACK_FILE).write_text(json.dumps(signed, indent=2) + "\n", encoding="utf-8")
    return signed


# PURPOSE: THE ATTESTATION KIND IN A PACK PATH SUCH AS attestations/01-<sha12>-policy-decision.dsse.json
def kind_of(path: str) -> str:
    return Path(path).name.removesuffix(".dsse.json").split("-", 2)[2]


# PURPOSE: EACH COMMIT'S PREDICATES BY KIND, READ FROM THE ATTESTATION FILES THE PACK STATEMENT LISTS
def evidence_of(folder: Path, predicate: dict) -> dict[str, dict[str, dict]]:
    found: dict[str, dict[str, dict]] = {}
    for item in predicate["attestations"]:
        body = payload_of(json.loads((folder / item["path"]).read_text(encoding="utf-8")))
        found.setdefault(item["commit"], {})[kind_of(item["path"])] = body["predicate"]
    return found


# PURPOSE: STATED ALGORITHMS WITH NO VALID SIGNATURE; A DISTRUSTED ONE IS EXCUSED, AS HYBRID SIGNING INTENDS
def unsigned(check: Verification, stated: set[str], policy: Policy) -> list[str]:
    return sorted(stated - {r.alg for r in check.results if r.status == "valid"} - policy.distrusted)


# PURPOSE: THE REPORT AND OSCAL FILES, BUILT FROM THE PACK PREDICATE AND THE ATTESTED PREDICATES ONLY
def derived(predicate: dict, evidence: dict[str, dict[str, dict]]) -> dict[str, bytes]:
    files = {REPORT: render(report_blocks(predicate, evidence), f"changeproof evidence pack: {predicate['release']}")}
    for n, (sha, kinds) in enumerate(evidence.items(), 1):
        doc = assessment_results_of(kinds["impact"], kinds["policy-decision"])
        validate_oscal(doc)
        files[f"oscal/{stem(n, sha)}.json"] = (json.dumps(doc, indent=2) + "\n").encode()
    return files


# PURPOSE: VERIFIES EVERY SIGNATURE AND DIGEST IN A PACK OFFLINE AND REBUILDS ITS REPORT AND OSCAL FILES
def verify_pack(folder: Path, trusted: list[PublicKey], policy: Policy) -> PackCheck:
    folder = Path(folder)
    envelope = json.loads((folder / PACK_FILE).read_text(encoding="utf-8"))
    signed = verify_envelope(envelope, trusted, policy)
    if not signed.ok:
        return PackCheck(False, [f"{PACK_FILE}: signature {r.alg} {r.status}" for r in signed.results
                                 if r.status != "valid"] + [f"{PACK_FILE}: no valid {a} signature" for a in signed.missing]
                         or [f"{PACK_FILE}: does not verify"], {})
    problems = []
    found = payload_of(envelope)
    if found["predicateType"] != PREDICATE_TYPES["evidence-pack"]:
        return PackCheck(False, [f"{PACK_FILE}: not an evidence pack ({found['predicateType']})"], {})
    predicate, subjects = found["predicate"], {s["name"]: s["digest"] for s in found["subject"]}
    crypto = predicate["crypto"]
    if crypto["signed_with"] != [{"alg": s.get("alg"), "keyid": s["keyid"]} for s in envelope["signatures"]]:
        problems.append(f"{PACK_FILE}: its signatures differ from the ones its crypto block lists")
    problems += [f"{PACK_FILE}: no valid {alg} signature, which its crypto block states"
                 for alg in unsigned(signed, {s["alg"] for s in crypto["signed_with"]}, policy)]
    for item in predicate["attestations"]:
        path = folder / item["path"]
        if not path.is_file():
            problems.append(f"{item['path']}: missing")
            continue
        attestation = json.loads(path.read_text(encoding="utf-8"))
        check = verify_envelope(attestation, trusted, policy)
        if not check.ok:
            problems.append(f"{item['path']}: signatures do not verify")
        problems += [f"{item['path']}: no valid {alg} signature, which the pack's crypto profile states"
                     for alg in unsigned(check, set(crypto.get("signing", [])), policy)]
        if digest(base64.b64decode(attestation["payload"])) != item["payload"]:
            problems.append(f"{item['path']}: payload differs from the one the pack statement lists")
    if problems:
        return PackCheck(False, problems, {})
    rebuilt = derived(predicate, evidence_of(folder, predicate))
    for name, expected in subjects.items():
        path = folder / name
        if name in rebuilt and digest(rebuilt[name]) != expected:
            problems.append(f"{name}: rebuilt from the attestations, it differs from the signed digest")
        if path.is_file() and digest(path.read_bytes()) != expected:
            problems.append(f"{name}: the file in the pack differs from the signed digest")
        elif not path.is_file() and name not in rebuilt:
            problems.append(f"{name}: missing")
    problems += [f"{name}: rebuilt but not listed in the pack statement" for name in rebuilt if name not in subjects]
    return PackCheck(not problems, problems, rebuilt)


# PURPOSE: FILE:LINE OR FILE:LINE-END FOR A PROVENANCE DICT
def where(provenance: dict) -> str:
    end = provenance.get("end_line")
    return f"{provenance['file']}:{provenance['line']}" + (f"-{end}" if end and end != provenance["line"] else "")


# PURPOSE: "AND N MORE" LINE FOR A LIST CUT TO THE REPORT'S LENGTH
def more(items: list, kind: str) -> list[tuple[str, str]]:
    return [("code", f"... and {len(items) - LISTED} more in the {kind} attestation")] if len(items) > LISTED else []


# PURPOSE: REPORT LINES FOR THE TESTS RUN INSIDE THE IMPACT SET: WHAT THE CHANGE ALTERED, PROGRAM BY PROGRAM
def inside_blocks(impact: dict, full: dict | None) -> list[tuple[str, str]]:
    if full is None:
        return [("text", "Inside the impact set: no full-suite attestation in this pack.")]
    gaps = {u["program"]: u for u in full.get("untested", []) if "program" in u}
    programs = sorted(impact_programs(impact, {t["target"]["name"] for t in full["tests"]} | set(gaps)))
    blocks = []
    for program in programs:
        if program in gaps:
            blocks.append(("text", f"Inside the impact set: {program} untested ({where(gaps[program]['provenance'])}): "
                                   f"{gaps[program]['reason']}"))
            continue
        tests = [t for t in full["tests"] if t["target"]["name"] == program]
        changed = [t for t in tests if t["result"] != "same"]
        blocks.append(("text", f"Inside the impact set: {program} {len(tests)} tests, {len(changed)} different"
                               + (": behaviour this change altered, to check against its ticket." if changed else
                                  ": no behaviour change found.")))
        blocks += [("code", f"{t['result']}: {program} test {t['id']} ({where(t['target']['provenance'])})")
                   for t in changed[:LISTED]] + more(changed, "full-suite")
    return blocks or [("text", "Inside the impact set: no program the tests can run.")]


# PURPOSE: REPORT LINES FOR ONE CHANGE: WHO AND WHY, WHAT IT TOUCHES, BEHAVIOUR INSIDE AND OUTSIDE IT, THE POLICY RULES
def change_blocks(n: int, total: int, sha: str, kinds: dict[str, dict]) -> list[tuple[str, str]]:
    impact, decision, tested = kinds["impact"], kinds["policy-decision"], kinds.get("behavioral-equivalence")
    tiers = [i["confidence"] for i in impact["impacted"]]
    blocks = [("heading", f"Change {n} of {total}: commit {sha[:12]}"), ("text", "Who and why")]
    blocks += [("code", f"{w['role']}: {w['id']} ({w['source']})") for w in impact["who"]]
    blocks += [("code", f"{w['kind']}: {w['ref']} ({w['found_in']})") for w in impact.get("why", [])] or [
        ("code", "no ticket or requirement is named in the commit")]
    blocks.append(("text", f"What it touches: {len(impact['changed'])} entities changed, {len(tiers)} impacted "
                           f"({tiers.count('definite')} definite, {tiers.count('probable')} probable, "
                           f"{tiers.count('possible')} possible), {len(impact['unresolved'])} gaps reported. "
                           f"Touches crypto: {'yes' if impact['touches_crypto'] else 'no'}."))
    blocks += [("code", f"{where(c['provenance'])}  {c['kind']} {c['name']} ({c['change']})")
               for c in impact["changed"][:LISTED]] + more(impact["changed"], "impact")
    blocks += [("code", f"{where(i['provenance'])}  {i['kind']} {i['name']} ({i['confidence']})")
               for i in impact["impacted"][:LISTED]] + more(impact["impacted"], "impact")
    blocks += [("code", f"relied on by {r['id']} through {r['via_component']}") for r in impact.get("reliant_systems", [])]
    blocks += inside_blocks(impact, kinds.get("full-suite"))
    if tested is None:
        blocks.append(("text", "Behaviour outside the impact set: no equivalence attestation in this pack."))
    else:
        s = tested["summary"]
        linked = tested["impact_statement"] == impact_statement_digest(impact)
        blocks.append(("text", f"Outside the impact set: {tested['verdict']}. {s['total']} tests ({tested['scope']}): "
                               f"{s['same']} same, {s['different']} different, {s['error']} errors."))
        blocks.append(("text", "Linked to this change's impact attestation by its digest." if linked else
                               "NOT linked to this change's impact attestation: the digests differ."))
        blocks += [("code", f"different: {t['target']['name']} test {t['id']} ({where(t['target']['provenance'])})")
                   for t in tested["tests"] if t["result"] != "same"]
        blocks += [("code", f"untested: {u.get('program', u['provenance']['file'])} ({where(u['provenance'])}): "
                            f"{u['reason']}") for u in tested.get("untested", [])]
    blocks.append(("text", f"Policy rules (OPA {decision['opa']}): {'all hold' if decision['ok'] else 'a rule fails'}."))
    for rule in decision["rules"]:
        blocks.append(("code", f"{rule['rule']}: {rule['status']}" + (f" ({rule['reason']})" if rule.get("reason") else "")))
        blocks += [("code", f"  {kind}: {m['message']} ({where(m['provenance'])})")
                   for kind in ("deny", "warn") for m in rule[kind]]
    return blocks


# PURPOSE: THE RELEASE VERDICT AND EVERY OPEN FINDING, SO AN ASSESSOR SEES WHAT BLOCKS THE RELEASE FIRST
def decision_blocks(evidence: dict[str, dict[str, dict]]) -> list[tuple[str, str]]:
    failing = [sha for sha, kinds in evidence.items() if not kinds["policy-decision"]["ok"]]
    blocks = [("heading", "Release decision"),
              ("text", f"Release decision: {len(failing)} of {len(evidence)} changes fail a policy rule."
                       if failing else f"Release decision: all {len(evidence)} changes pass every policy rule.")]
    for sha, kinds in evidence.items():
        for rule in kinds["policy-decision"]["rules"]:
            blocks += [("code", f"open: {sha[:12]} {rule['rule']}: {m['message']} ({where(m['provenance'])})")
                       for m in rule["deny"]]
            if rule["status"] in ("inconclusive", "not-evaluated"):
                blocks.append(("code", f"open: {sha[:12]} {rule['rule']}: {rule['status']}"
                                       + (f" ({rule['reason']})" if rule.get("reason") else "")))
    return blocks


# PURPOSE: EACH CONTROL IN SCOPE, WHETHER ITS NUMBER WAS CHECKED AT SOURCE, AND THE ENGINE EVIDENCE THAT ANSWERS IT
def control_blocks(evidence: dict[str, dict[str, dict]]) -> list[tuple[str, str]]:
    frameworks = dict.fromkeys(f for kinds in evidence.values() for f in kinds["policy-decision"]["frameworks"])
    blocks = [("heading", "Controls this evidence answers"),
              ("text", "Mapped by the engine's framework table. A control number marked unverified has not been "
                       "read in its source yet. Planned evidence is not in this pack.")]
    for framework in frameworks:
        label = FRAMEWORK_LABELS.get(framework, framework)
        if not (controls := controls_for(framework)):
            blocks.append(("code", f"{label}: no controls mapped ({NOT_MAPPED.get(framework, 'not in the table')})"))
            continue
        for c in controls:
            status = f"checked {c.source.checked}" if c.source.checked else "unverified"
            name = c.id if c.id.startswith(label) else f"{label} {c.id}"
            blocks.append(("code", f"{name} (source {status}): {c.topic}"))
            blocks += [("code", f"  {e.output}" + (" (planned)" if e.proof == PLANNED else "")) for e in c.evidence]
    return blocks


# PURPOSE: THE WHOLE REPORT: COVER, RELEASE DECISION, HOW TO CHECK IT, THE CRYPTO PROFILE, EACH CHANGE, THE CONTROLS
def report_blocks(predicate: dict, evidence: dict[str, dict[str, dict]]) -> list[tuple[str, str]]:
    change, crypto = predicate["change"], predicate["crypto"]
    blocks = [
        ("title", f"changeproof evidence pack: {predicate['release']}"),
        ("text", f"Repository: {change['repository']}"),
        ("text", f"Commits {change['base'][:12]}..{change['head'][:12]}: {len(evidence)} changes. "
                 f"Generated {predicate['generated_at']} by changeproof {predicate['engine']['version']}."),
        *decision_blocks(evidence),
        ("heading", "How to check this pack"),
        ("text", "Everything in this report is read from the signed attestations in the attestations folder, and "
                 "nothing else. Run: changeproof pack-verify <pack folder> --trust <public key> ... It verifies "
                 "every signature offline and rebuilds this report and the OSCAL files from the attestations; "
                 "each must match the digest in pack.dsse.json byte for byte."),
        ("text", "Behavioral equivalence means the characterization tests found no difference. It is evidence "
                 "from tests, not a proof for all inputs. Programs it could not test are listed."),
        ("heading", "Crypto profile"),
        ("text", f"Crypto profile: {crypto['profile'] or 'none configured'}"),
    ]
    if crypto["profile"]:
        blocks.append(("code", f"evidence signing: {', '.join(crypto['signing'])}; release signing: "
                               f"{crypto['release_signing']}; hash: {crypto['hash']}"))
    release = [s for s in crypto["signed_with"]
               if s["alg"] == crypto.get("release_signing") and s["alg"] not in crypto.get("signing", [])]
    blocks += [("code", f"this pack is signed with {s['alg']} (key {s['keyid'][:16]})")
               for s in crypto["signed_with"] if s not in release]
    blocks += [("code", f"release signature: {s['alg']} (key {s['keyid'][:16]})") for s in release]
    if crypto["profile"] and not release:
        blocks.append(("code", f"release signature: none; the profile names {crypto['release_signing']}"))
    for n, (sha, kinds) in enumerate(evidence.items(), 1):
        blocks += change_blocks(n, len(evidence), sha, kinds)
    blocks += control_blocks(evidence)
    blocks.append(("heading", "Attestations"))
    blocks += [("code", f"{a['path']}  {next(iter(a['payload'].values()))[:24]}") for a in predicate["attestations"]]
    return blocks
