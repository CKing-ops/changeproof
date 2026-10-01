"""DSSE envelopes: one signature per algorithm over the same payload (ADR 002 decisions 3, 4 and 6).

Each signature entry carries, beside DSSE's `keyid` and `sig`, the algorithm ID, the library and
version that made it, and when. Those labels are not trusted: verification takes the algorithm from
the trusted key with that ID, and a label that disagrees fails.
"""

import base64
import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from changeproof.signer.algorithms import ALGORITHMS, digest
from changeproof.signer.keys import PrivateKey, PublicKey

PAYLOAD_TYPE = "application/vnd.in-toto+json"


@dataclass(frozen=True)
class Policy:
    distrusted: frozenset[str] = frozenset()  # algorithm IDs whose signatures no longer count
    required: frozenset[str] = frozenset()  # algorithm IDs that must have a valid signature


@dataclass(frozen=True)
class SignatureResult:
    keyid: str
    alg: str
    status: str  # valid | invalid | distrusted | unknown-key | algorithm-mismatch


@dataclass(frozen=True)
class Verification:
    results: list[SignatureResult]
    missing: list[str] = field(default_factory=list)  # required algorithms with no valid signature

    # PURPOSE: TRUE WHEN NO TRUSTED SIGNATURE FAILS, ONE AT LEAST HOLDS AND NOTHING REQUIRED IS MISSING
    @property
    def ok(self) -> bool:
        statuses = {r.status for r in self.results}
        return "valid" in statuses and not statuses & {"invalid", "algorithm-mismatch"} and not self.missing


# PURPOSE: DSSE PRE-AUTHENTICATION ENCODING; THE BYTES EVERY SIGNATURE COVERS
def pae(payload_type: str, payload: bytes) -> bytes:
    kind = payload_type.encode()
    return b"DSSEv1 %d %s %d %s" % (len(kind), kind, len(payload), payload)


# PURPOSE: UTC TIMESTAMP IN THE FORM SIGNATURES RECORD
def stamp(at: datetime) -> str:
    return at.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


# PURPOSE: ONE SIGNATURE ENTRY OVER THE ENCODED PAYLOAD
def signature(key: PrivateKey, message: bytes, at: datetime) -> dict:
    return {"keyid": key.keyid, "sig": base64.b64encode(key.sign(message)).decode(), "alg": key.alg,
            "library": key.algorithm.library, "signed_at": stamp(at)}


# PURPOSE: SIGNS A JSON PAYLOAD WITH EVERY KEY, IN ORDER, INTO ONE ENVELOPE
def sign_envelope(payload: dict, keys: list[PrivateKey], at: datetime) -> dict:
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    message = pae(PAYLOAD_TYPE, body)
    return {"payloadType": PAYLOAD_TYPE, "payload": base64.b64encode(body).decode(),
            "signatures": [signature(k, message, at) for k in keys]}


# PURPOSE: CHECKS EVERY SIGNATURE AGAINST THE TRUSTED KEYS UNDER THE POLICY, FULLY OFFLINE
def verify_envelope(envelope: dict, trusted: list[PublicKey], policy: Policy) -> Verification:
    keys = {k.keyid: k for k in trusted}
    message = pae(envelope["payloadType"], base64.b64decode(envelope["payload"]))
    results = []
    for entry in envelope["signatures"]:
        key = keys.get(entry["keyid"])
        if key is None:
            status = "unknown-key"
        elif entry.get("alg") != key.alg:
            status = "algorithm-mismatch"
        elif key.alg in policy.distrusted:
            status = "distrusted"
        elif key.alg in ALGORITHMS and ALGORITHMS[key.alg].verify(key.public, message, base64.b64decode(entry["sig"])):
            status = "valid"
        else:
            status = "invalid"
        results.append(SignatureResult(entry["keyid"], key.alg if key else entry.get("alg", ""), status))
    held = {r.alg for r in results if r.status == "valid"}
    return Verification(results, sorted(policy.required - held))


# PURPOSE: COUNTERSIGNS VERIFIED EVIDENCE WITH NEW KEYS, KEEPING PAYLOAD AND EARLIER SIGNATURES BYTE FOR BYTE
def resign(envelope: dict, keys: list[PrivateKey], trusted: list[PublicKey], policy: Policy, at: datetime,
           log: Path | None = None) -> dict:
    if not verify_envelope(envelope, trusted, policy).ok:
        raise ValueError("the envelope does not verify; re-signing would vouch for it")
    payload = base64.b64decode(envelope["payload"])
    message = pae(envelope["payloadType"], payload)
    added = [signature(k, message, at) for k in keys]
    if log:
        with Path(log).open("a", encoding="utf-8") as out:
            out.write(json.dumps({"at": stamp(at), "payload_digest": digest(payload),
                                  "added": [{"alg": s["alg"], "keyid": s["keyid"]} for s in added]}) + "\n")
    return envelope | {"signatures": envelope["signatures"] + added}
