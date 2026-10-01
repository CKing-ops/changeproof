"""Assessor evidence pack for a release (ROADMAP Week 12).

For each commit in the release the pack holds three signed attestations: impact, policy decision
and behavioral equivalence. The PDF report and the OSCAL assessment results are built from those
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
from changeproof.equivalence import change_subject, equivalence_of, impact_statement_digest
from changeproof.gate import gate, policy_decision
from changeproof.impact.run import CONFIG_NAME
from changeproof.oscal import assessment_results_of, validate_oscal
from changeproof.pack.pdf import render
from changeproof.predicates import PREDICATE_TYPES, statement, validate_predicate
from changeproof.signer import Policy, PrivateKey, PublicKey, digest, sign_envelope, verify_envelope

PACK_FILE = "pack.dsse.json"
REPORT = "report.pdf"
KINDS = ("impact", "policy-decision", "behavioral-equivalence")  # RENAME: ATTESTATIONS KEPT FOR EACH COMMIT
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


# PURPOSE: BUILDS THE PACK FOR A RELEASE INTO A NEW FOLDER, SIGNING EVERY ATTESTATION AND THE PACK STATEMENT
def build_pack(root: Path, revisions: str, out: Path, keys: list[PrivateKey], release: str | None = None,
               copybook_dirs: list[str] = (), config_path: str = CONFIG_NAME, at: datetime | None = None,
               runner: Runner | None = None) -> dict:
    root, out, at = Path(root), Path(out), at or datetime.now(UTC)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError(f"{out} is not empty")
    (out / "attestations").mkdir(parents=True, exist_ok=True)
    listed, changes = [], []
    for n, sha in enumerate(commits_in(root, revisions), 1):
        result = gate(root, sha, copybook_dirs, config_path)
        tested = result.equivalence or equivalence_of(result.run, root, copybook_dirs, runner=runner)
        config, engine = result.run.config, result.run.predicate["engine"]
        changes.append(result.run.predicate["change"])
        bodies = dict(zip(KINDS, (result.run.predicate, policy_decision(result, at), tested.predicate)))
        for kind, body in bodies.items():
            found = statement([change_subject(body)], PREDICATE_TYPES[kind], body)
            path = f"attestations/{stem(n, sha)}-{kind}.dsse.json"
            (out / path).write_text(json.dumps(sign_envelope(found, keys, at), indent=2) + "\n", encoding="utf-8")
            listed.append({"path": path, "predicate_type": PREDICATE_TYPES[kind], "commit": sha,
                           "payload": digest(canonical(found))})
    crypto = {"profile": config.crypto.profile, "signing": list(config.crypto.signing),
              "release_signing": config.crypto.release_signing, "hash": config.crypto.hash} if config else {"profile": None}
    predicate = {
        "release": release or revisions,
        "change": changes[0] | {"head": changes[-1]["head"]},
        "crypto": crypto | {"signed_with": [{"alg": k.alg, "keyid": k.keyid} for k in keys]},
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
    signed = sign_envelope(statement(subjects, PREDICATE_TYPES["evidence-pack"], predicate), keys, at)
    (out / PACK_FILE).write_text(json.dumps(signed, indent=2) + "\n", encoding="utf-8")
    return signed


# PURPOSE: EACH COMMIT'S PREDICATES BY KIND, READ FROM THE ATTESTATION FILES THE PACK STATEMENT LISTS
def evidence_of(folder: Path, predicate: dict) -> dict[str, dict[str, dict]]:
    found: dict[str, dict[str, dict]] = {}
    for item in predicate["attestations"]:
        body = payload_of(json.loads((folder / item["path"]).read_text(encoding="utf-8")))
        kind = next(k for k, t in PREDICATE_TYPES.items() if t == item["predicate_type"])
        found.setdefault(item["commit"], {})[kind] = body["predicate"]
    return found


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
    for item in predicate["attestations"]:
        path = folder / item["path"]
        if not path.is_file():
            problems.append(f"{item['path']}: missing")
            continue
        attestation = json.loads(path.read_text(encoding="utf-8"))
        check = verify_envelope(attestation, trusted, policy)
        if not check.ok:
            problems.append(f"{item['path']}: signatures do not verify")
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


# PURPOSE: REPORT LINES FOR ONE CHANGE: WHO AND WHY, WHAT IT TOUCHES, BEHAVIOUR OUTSIDE IT, AND THE POLICY RULES
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


# PURPOSE: THE WHOLE REPORT: COVER, HOW TO CHECK IT, THE CRYPTO PROFILE, THEN EACH CHANGE
def report_blocks(predicate: dict, evidence: dict[str, dict[str, dict]]) -> list[tuple[str, str]]:
    change, crypto = predicate["change"], predicate["crypto"]
    blocks = [
        ("title", f"changeproof evidence pack: {predicate['release']}"),
        ("text", f"Repository: {change['repository']}"),
        ("text", f"Commits {change['base'][:12]}..{change['head'][:12]}: {len(evidence)} changes. "
                 f"Generated {predicate['generated_at']} by changeproof {predicate['engine']['version']}."),
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
    blocks += [("code", f"this pack is signed with {s['alg']} (key {s['keyid'][:16]})") for s in crypto["signed_with"]]
    for n, (sha, kinds) in enumerate(evidence.items(), 1):
        blocks += change_blocks(n, len(evidence), sha, kinds)
    blocks.append(("heading", "Attestations"))
    blocks += [("code", f"{a['path']}  {next(iter(a['payload'].values()))[:24]}") for a in predicate["attestations"]]
    return blocks
