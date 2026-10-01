"""Week 6: the signer interface, DSSE envelopes, verification policy and re-signing (ADR 002)."""

import base64
import json
import stat
from datetime import UTC, datetime

import pytest
import yaml

from changeproof.config import Config
from changeproof.predicates import PREDICATE_TYPES, statement
from changeproof.signer import (
    ALGORITHMS,
    HASHES,
    PAYLOAD_TYPE,
    Policy,
    check_crypto,
    digest,
    generate_key,
    load_private,
    load_public,
    resign,
    sign_envelope,
    verify_envelope,
)

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
LATER = datetime(2031, 1, 1, 9, 0, tzinfo=UTC)
ROADMAP_PROFILES = {  # the four signer setups ROADMAP Week 6 names
    "classical": ["ecdsa-p384"],
    "ml-dsa-87": ["ml-dsa-87"],
    "hybrid": ["ml-dsa-87", "ecdsa-p384"],
    "lms": ["lms-sha256-192"],
}


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    folder = tmp_path_factory.mktemp("keys")
    return {alg: generate_key(alg, folder / alg) for alg in ALGORITHMS}


@pytest.fixture
def payload():
    return statement([{"name": "INVMAIN.cbl", "digest": digest(b"PROGRAM-ID. INVMAIN.")}],
                     PREDICATE_TYPES["impact"], json.loads(open("tests/fixtures/predicates/impact.json").read()))


def keys_for(keys, setup):
    return [load_private(keys[alg].private_path) for alg in ROADMAP_PROFILES[setup]]


def trusted(keys):
    return [load_public(k.public_path) for k in keys.values()]


def tampered(envelope, **changes):
    return json.loads(json.dumps(envelope)) | changes


def test_the_registry_names_classical_and_post_quantum_algorithms():
    assert {a.id: a.family for a in ALGORITHMS.values()} == {
        "ecdsa-p384": "classical", "ml-dsa-87": "post-quantum", "lms-sha256-192": "post-quantum"}
    assert ALGORITHMS["lms-sha256-192"].stateful
    assert set(HASHES) == {"sha-384", "sha-256"}


def test_digests_are_sha_384_digest_sets():
    found = digest(b"abc")
    assert list(found) == ["sha-384"]
    assert found["sha-384"].startswith("cb00753f45a35e8b")
    assert len(found["sha-384"]) == 96


@pytest.mark.parametrize("setup", ROADMAP_PROFILES)
def test_signed_envelopes_verify_offline(keys, payload, setup):
    envelope = sign_envelope(payload, keys_for(keys, setup), NOW)
    assert envelope["payloadType"] == PAYLOAD_TYPE
    assert json.loads(base64.b64decode(envelope["payload"])) == payload
    assert verify_envelope(envelope, trusted(keys), Policy()).ok


@pytest.mark.parametrize("setup", ROADMAP_PROFILES)
def test_exit_check_tampering_fails_under_every_profile(keys, payload, setup):
    envelope = sign_envelope(payload, keys_for(keys, setup), NOW)
    changed = payload | {"predicate": payload["predicate"] | {"touches_crypto": True}}
    body = base64.b64encode(json.dumps(changed).encode()).decode()
    flipped = base64.b64decode(envelope["signatures"][0]["sig"])
    flipped = base64.b64encode(bytes([flipped[0] ^ 1]) + flipped[1:]).decode()
    attempts = [
        tampered(envelope, payload=body),
        tampered(envelope, payloadType="application/json"),
        tampered(envelope, signatures=[envelope["signatures"][0] | {"sig": flipped}] + envelope["signatures"][1:]),
    ]
    for attempt in attempts:
        assert not verify_envelope(attempt, trusted(keys), Policy()).ok


def test_every_signature_records_its_algorithm_library_and_time(keys, payload):
    envelope = sign_envelope(payload, keys_for(keys, "hybrid"), NOW)
    assert [s["alg"] for s in envelope["signatures"]] == ["ml-dsa-87", "ecdsa-p384"]
    for sig in envelope["signatures"]:
        assert sig["keyid"] == keys[sig["alg"]].keyid
        assert sig["library"].startswith("cryptography ")
        assert sig["signed_at"] == "2026-10-01T09:00:00Z"
    lms = sign_envelope(payload, keys_for(keys, "lms"), NOW)["signatures"][0]
    assert lms["library"] == "pyhsslms 2.0.0"


@pytest.mark.parametrize("distrusted", [{"ecdsa-p384"}, {"ml-dsa-87"}])
def test_exit_check_hybrid_verifies_when_either_component_is_distrusted(keys, payload, distrusted):
    envelope = sign_envelope(payload, keys_for(keys, "hybrid"), NOW)
    result = verify_envelope(envelope, trusted(keys), Policy(distrusted=frozenset(distrusted)))
    assert result.ok
    assert sorted(r.status for r in result.results) == ["distrusted", "valid"]


def test_hybrid_fails_when_both_components_are_distrusted(keys, payload):
    envelope = sign_envelope(payload, keys_for(keys, "hybrid"), NOW)
    assert not verify_envelope(envelope, trusted(keys), Policy(distrusted=frozenset({"ecdsa-p384", "ml-dsa-87"}))).ok


def test_a_distrusted_component_never_hides_tampering(keys, payload):
    envelope = sign_envelope(payload, keys_for(keys, "hybrid"), NOW)
    body = base64.b64encode(b'{"_type": "forged"}').decode()
    assert not verify_envelope(tampered(envelope, payload=body), trusted(keys),
                               Policy(distrusted=frozenset({"ecdsa-p384"}))).ok


def test_the_algorithm_comes_from_the_trusted_key_not_the_label(keys, payload):
    envelope = sign_envelope(payload, keys_for(keys, "classical"), NOW)
    relabelled = tampered(envelope, signatures=[envelope["signatures"][0] | {"alg": "ml-dsa-87"}])
    result = verify_envelope(relabelled, trusted(keys), Policy())
    assert not result.ok
    assert result.results[0].status == "algorithm-mismatch"


def test_signatures_from_unknown_keys_do_not_count(keys, payload, tmp_path):
    stranger = load_private(generate_key("ecdsa-p384", tmp_path / "stranger").private_path)
    envelope = sign_envelope(payload, [stranger], NOW)
    result = verify_envelope(envelope, trusted(keys), Policy())
    assert not result.ok
    assert result.results[0].status == "unknown-key"


def test_a_policy_can_require_an_algorithm(keys, payload):
    envelope = sign_envelope(payload, keys_for(keys, "hybrid"), NOW)
    stripped = tampered(envelope, signatures=[s for s in envelope["signatures"] if s["alg"] != "ml-dsa-87"])
    assert verify_envelope(stripped, trusted(keys), Policy()).ok
    result = verify_envelope(stripped, trusted(keys), Policy(required=frozenset({"ml-dsa-87"})))
    assert not result.ok
    assert result.missing == ["ml-dsa-87"]


def test_private_keys_are_written_owner_only(keys):
    for key in keys.values():
        assert stat.S_IMODE(key.private_path.stat().st_mode) == 0o600
        assert load_public(key.public_path).keyid == key.keyid


def test_lms_state_is_saved_before_the_signature_is_returned(tmp_path, payload):
    path = generate_key("lms-sha256-192", tmp_path / "release").private_path
    first = sign_envelope(payload, [load_private(path)], NOW)["signatures"][0]["sig"]
    second = sign_envelope(payload, [load_private(path)], NOW)["signatures"][0]["sig"]
    leaf = lambda sig: int.from_bytes(base64.b64decode(sig)[:4], "big")  # noqa: E731
    assert (leaf(first), leaf(second)) == (0, 1)
    assert load_private(path).remaining == 1022


def test_resign_countersigns_without_altering_the_original(keys, payload, tmp_path):
    original = sign_envelope(payload, keys_for(keys, "classical"), NOW)
    log = tmp_path / "resign.log"
    countersigned = resign(original, keys_for(keys, "ml-dsa-87"), trusted(keys), Policy(), LATER, log)
    assert countersigned["payload"] == original["payload"]
    assert countersigned["payloadType"] == original["payloadType"]
    assert countersigned["signatures"][0] == original["signatures"][0]
    assert countersigned["signatures"][1]["alg"] == "ml-dsa-87"
    assert countersigned["signatures"][1]["signed_at"] == "2031-01-01T09:00:00Z"
    assert verify_envelope(countersigned, trusted(keys), Policy(distrusted=frozenset({"ecdsa-p384"}))).ok
    assert verify_envelope(original, trusted(keys), Policy()).ok
    entry = json.loads(log.read_text().splitlines()[-1])
    assert entry["payload_digest"] == digest(base64.b64decode(original["payload"]))
    assert entry["added"] == [{"alg": "ml-dsa-87", "keyid": keys["ml-dsa-87"].keyid}]
    assert entry["at"] == "2031-01-01T09:00:00Z"


def test_resign_refuses_evidence_that_does_not_verify(keys, payload):
    original = sign_envelope(payload, keys_for(keys, "classical"), NOW)
    forged = tampered(original, payload=base64.b64encode(b'{"_type": "forged"}').decode())
    with pytest.raises(ValueError, match="does not verify"):
        resign(forged, keys_for(keys, "ml-dsa-87"), trusted(keys), Policy(), LATER)


def with_crypto(**crypto):
    raw = yaml.safe_load(open("docs/examples/changeproof.yaml"))
    raw["crypto"] |= crypto
    return Config.model_validate(raw).crypto


@pytest.mark.parametrize("example", ["changeproof", "carddemo", "eu-dora", "us-defense"])
def test_example_configs_pass_the_registry(example):
    raw = yaml.safe_load(open(f"docs/examples/{example}.yaml"))
    assert check_crypto(Config.model_validate(raw).crypto) == []


@pytest.mark.parametrize(("crypto", "problem"), [
    ({"signing": ["ml-dsa-78"]}, "crypto.signing: unknown algorithm 'ml-dsa-78'"),
    ({"hash": "sha-1"}, "crypto.hash: unknown hash 'sha-1'"),
    ({"hash": "sha-256"}, "crypto.hash: profile 'hybrid' does not allow 'sha-256'"),
    ({"profile": "quantum-proof"}, "crypto.profile: unknown profile 'quantum-proof'"),
    ({"signing": ["ml-dsa-87"]}, "crypto.signing: profile 'hybrid' needs a classical algorithm"),
    ({"profile": "nist-pqc"}, "crypto.signing: profile 'nist-pqc' does not allow 'ecdsa-p384'"),
    ({"profile": "cnsa2", "release_signing": "ecdsa-p384"},
     "crypto.release_signing: profile 'cnsa2' does not allow 'ecdsa-p384'"),
    ({"release_signing": "sha-384"}, "crypto.release_signing: unknown algorithm 'sha-384'"),
])
def test_the_registry_checks_config_algorithms_against_the_profile(crypto, problem):
    assert any(p.startswith(problem) for p in check_crypto(with_crypto(**crypto)))
