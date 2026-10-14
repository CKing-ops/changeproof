"""Week 12: the assessor evidence pack. Exit check: the pack reconstructs offline from attestations alone."""

import base64
import importlib.util
import io
import json
import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pypdf import PdfReader

from changeproof.characterize import LocalRunner
from changeproof.cli import main
from changeproof.oscal import validate_oscal
from changeproof.pack import PACK_FILE, REPORT, build_pack, verify_pack
from changeproof.predicates import PREDICATE_TYPES
from changeproof.signer import Policy, digest, generate_key, load_private, load_public, verify_envelope

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

_spec = importlib.util.spec_from_file_location("pack_seed", Path(__file__).parent / "fixtures" / "pack" / "seed.py")
_seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_seed)


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    folder = tmp_path_factory.mktemp("keys")
    return [generate_key(alg, folder / alg) for alg in ("ml-dsa-87", "ecdsa-p384")]


@pytest.fixture(scope="module")
def release_key(tmp_path_factory):
    return generate_key("lms-sha256-192", tmp_path_factory.mktemp("release") / "lms")


@pytest.fixture(scope="module")
def built(tmp_path_factory, keys, release_key):
    root = tmp_path_factory.mktemp("pack") / "repo"
    shas = _seed.seed(root)
    out = tmp_path_factory.mktemp("out") / "v1.4"
    build_pack(root, f"{shas['base']}..{shas['co-authored']}", out, [load_private(k.private_path) for k in keys],
               release="v1.4", at=NOW, runner=LocalRunner(), release_key=load_private(release_key.private_path))
    return out, shas


@pytest.fixture(scope="module")
def cnsa2(tmp_path_factory, keys, release_key):
    root = tmp_path_factory.mktemp("cnsa2") / "repo"
    shas = _seed.seed(root, "us-defense-cnsa2")
    out = tmp_path_factory.mktemp("out") / "cnsa2"
    build_pack(root, f"{shas['base']}..{shas['co-authored']}", out, [load_private(keys[0].private_path)],
               release="v1.4", at=NOW, runner=LocalRunner(), release_key=load_private(release_key.private_path))
    return out, shas


def trusted(keys, release_key=None):
    return [load_public(k.public_path) for k in [*keys, *([release_key] if release_key else [])]]


def payload(path: Path) -> dict:
    return json.loads(base64.b64decode(json.loads(path.read_text())["payload"]))


def report_text(data: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


def test_the_pack_holds_signed_attestations_a_report_and_oscal_for_every_change(built):
    out, shas = built
    names = sorted(p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file())
    stem = {n: f"{i:02d}-{shas[n][:12]}" for i, n in enumerate(("assisted", "co-authored"), 1)}
    assert names == sorted([PACK_FILE, REPORT] + [f"oscal/{s}.json" for s in stem.values()] + [
        f"attestations/{s}-{kind}.dsse.json" for s in stem.values()
        for kind in ("impact", "policy-decision", "behavioral-equivalence", "full-suite")])
    for path in (out / "oscal").iterdir():
        validate_oscal(json.loads(path.read_text()))


def test_the_pack_states_its_crypto_profile_and_the_algorithms_that_signed_it(built, keys, release_key):
    out, _ = built
    statement = payload(out / PACK_FILE)
    assert statement["predicateType"] == PREDICATE_TYPES["evidence-pack"]
    crypto = statement["predicate"]["crypto"]
    assert crypto | {"signed_with": None} == {"profile": "hybrid", "signing": ["ml-dsa-87", "ecdsa-p384"],
                                               "release_signing": "lms-sha256-192", "hash": "sha-384", "signed_with": None}
    assert crypto["signed_with"] == [{"alg": load_public(k.public_path).alg, "keyid": k.keyid}
                                     for k in [*keys, release_key]]
    text = report_text((out / REPORT).read_bytes())
    assert "Crypto profile: hybrid" in text and "ml-dsa-87" in text and "ecdsa-p384" in text
    assert f"release signature: lms-sha256-192 (key {release_key.keyid[:16]})" in text


def test_exit_check_the_pack_reconstructs_offline_from_attestations_alone(built, keys, release_key, tmp_path):
    out, _ = built
    alone = tmp_path / "alone"
    shutil.copytree(out / "attestations", alone / "attestations")
    shutil.copy(out / PACK_FILE, alone / PACK_FILE)
    check = verify_pack(alone, trusted(keys, release_key), Policy())
    assert check.ok, check.problems
    original = {p.relative_to(out).as_posix(): p.read_bytes() for p in [out / REPORT, *(out / "oscal").iterdir()]}
    assert check.rebuilt == original


def test_a_complete_pack_verifies_and_every_file_matches_its_signed_digest(built, keys, release_key):
    out, _ = built
    check = verify_pack(out, trusted(keys, release_key), Policy(required=frozenset({"ml-dsa-87", "ecdsa-p384"})))
    assert check.ok, check.problems
    subjects = {s["name"]: s["digest"] for s in payload(out / PACK_FILE)["subject"]}
    assert set(subjects) == {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()} - {PACK_FILE}
    assert all(digest((out / name).read_bytes()) == d for name, d in subjects.items())


def test_the_hybrid_pack_still_verifies_when_one_algorithm_is_distrusted(built, keys, release_key):
    out, _ = built
    assert verify_pack(out, trusted(keys, release_key), Policy(distrusted=frozenset({"ecdsa-p384"}))).ok


@pytest.mark.parametrize("target", ["report", "attestation", "oscal"])
def test_tampering_with_any_file_fails_the_check(built, keys, release_key, tmp_path, target):
    out, shas = built
    copy = tmp_path / "copy"
    shutil.copytree(out, copy)
    if target == "report":
        (copy / REPORT).write_bytes((copy / REPORT).read_bytes().replace(b"hybrid", b"hybrlD"))
    elif target == "oscal":
        path = copy / "oscal" / f"02-{shas['co-authored'][:12]}.json"
        assert "not-satisfied" in path.read_text()
        path.write_text(path.read_text().replace("not-satisfied", "satisfied"))
    else:
        path = copy / "attestations" / f"02-{shas['co-authored'][:12]}-policy-decision.dsse.json"
        envelope = json.loads(path.read_text())
        body = json.loads(base64.b64decode(envelope["payload"]))
        body["predicate"]["ok"] = True
        envelope["payload"] = base64.b64encode(json.dumps(body).encode()).decode()
        path.write_text(json.dumps(envelope))
    check = verify_pack(copy, trusted(keys, release_key), Policy())
    assert not check.ok
    assert check.problems


def test_the_report_joins_impact_and_equivalence_for_each_change(built):
    out, shas = built
    text = report_text((out / REPORT).read_bytes())
    for name in ("assisted", "co-authored"):
        assert shas[name][:12] in text
    assert "FEECALC" in text
    assert "Outside the impact set: equivalent" in text
    assert text.count("Linked to this change's impact attestation by its digest.") == 2
    assert "agent: feebot@tools.example (Assisted-by trailer" in text
    assert "agent-changes-need-independent-approval: fail" in text
    assert "noreply@anthropic.com took part in this change and no independent approver is recorded" in text


def test_the_equivalence_attestation_names_the_impact_attestation_beside_it(built):
    out, shas = built
    stem = f"01-{shas['assisted'][:12]}"
    impact = payload(out / "attestations" / f"{stem}-impact.dsse.json")
    equivalence = payload(out / "attestations" / f"{stem}-behavioral-equivalence.dsse.json")
    decision = payload(out / "attestations" / f"{stem}-policy-decision.dsse.json")
    linked = digest(json.dumps(impact, sort_keys=True, separators=(",", ":")).encode())
    assert equivalence["predicate"]["impact_statement"] == decision["predicate"]["impact_statement"] == linked


def test_the_cli_builds_and_verifies_a_pack(built, keys, release_key, tmp_path, capsys):
    out, shas = built
    root = tmp_path / "repo"
    _seed.seed(root)
    assert main(["pack", f"{shas['base']}..{shas['assisted']}", "--repo", str(root), "--out", str(tmp_path / "cli"),
                 *[a for k in keys for a in ("--key", str(k.private_path))],
                 "--release-key", str(release_key.private_path)]) == 0
    assert json.loads(capsys.readouterr().out)["attestations"] == 4
    assert main(["pack-verify", str(out), *[a for k in [*keys, release_key] for a in ("--trust", str(k.public_path))],
                 "--rebuild", str(tmp_path / "rebuilt")]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert (tmp_path / "rebuilt" / REPORT).read_bytes() == (out / REPORT).read_bytes()
    assert main(["pack-verify", str(out), "--trust", str(keys[0].public_path), "--require", "ecdsa-p384"]) == 1


def test_the_sample_pack_kept_in_the_repository_verifies_and_rebuilds():
    sample = Path(__file__).resolve().parent.parent / "docs" / "weekly"
    keys = [load_public(p) for p in sorted((sample / "week12-pack-keys").glob("*.pub.json"))]
    check = verify_pack(sample / "week12-pack", keys, Policy(required=frozenset({"ml-dsa-87", "ecdsa-p384"})))
    assert check.ok, check.problems


# Week 13: the top five objections from the mock assessor review (docs/weekly/week13-review.md)


def test_the_report_opens_with_the_release_decision_and_its_open_findings(built):
    out, shas = built
    text = report_text((out / REPORT).read_bytes())
    opening = text[:text.index("Change 1 of 2")]
    assert "Release decision: 1 of 2 changes fail a policy rule" in opening
    assert (f"open: {shas['co-authored'][:12]} agent-changes-need-independent-approval: noreply@anthropic.com took "
            "part in this change and no independent approver is recorded") in " ".join(opening.split())


def test_the_report_shows_the_tests_run_inside_the_impact_set_and_what_they_changed(built):
    out, shas = built
    text = " ".join(report_text((out / REPORT).read_bytes()).split())
    for n, name in enumerate(("assisted", "co-authored"), 1):
        stem = f"{n:02d}-{shas[name][:12]}"
        full = payload(out / "attestations" / f"{stem}-full-suite.dsse.json")["predicate"]
        impact = payload(out / "attestations" / f"{stem}-impact.dsse.json")
        assert full["scope"] == "full-suite"
        assert full["impact_statement"] == digest(json.dumps(impact, sort_keys=True, separators=(",", ":")).encode())
        inside = [t for t in full["tests"] if t["target"]["name"] == "FEECALC"]
        changed = sum(t["result"] == "different" for t in inside)
        assert f"Inside the impact set: FEECALC {len(inside)} tests, {changed} different" in text
    assert "0 different" in text.split("Change 2 of 2")[0].split("Inside the impact set")[1]
    assert "behaviour this change altered" in text.split("Change 2 of 2")[1]


def test_the_pack_refuses_keys_that_do_not_match_the_configured_signing(built, keys, tmp_path):
    root = tmp_path / "repo"
    shas = _seed.seed(root)
    with pytest.raises(ValueError, match="ml-dsa-87"):
        build_pack(root, shas["assisted"], tmp_path / "out", [load_private(keys[1].private_path)], at=NOW,
                   runner=LocalRunner())
    with pytest.raises(ValueError, match="release_signing"):
        build_pack(root, shas["assisted"], tmp_path / "out2", [load_private(k.private_path) for k in keys], at=NOW,
                   runner=LocalRunner(), release_key=load_private(keys[1].private_path))


@pytest.mark.parametrize("target", ["pack", "attestation"])
def test_a_pack_missing_a_signature_its_profile_states_fails_the_check(built, keys, release_key, tmp_path, target):
    out, shas = built
    copy = tmp_path / "copy"
    shutil.copytree(out, copy)
    path = copy / PACK_FILE if target == "pack" else copy / "attestations" / f"01-{shas['assisted'][:12]}-impact.dsse.json"
    envelope = json.loads(path.read_text())
    envelope["signatures"] = [s for s in envelope["signatures"] if s["alg"] != "ml-dsa-87"]
    path.write_text(json.dumps(envelope))
    check = verify_pack(copy, trusted(keys, release_key), Policy())
    assert not check.ok
    assert any("ml-dsa-87" in problem for problem in check.problems)


def test_the_report_maps_its_evidence_to_the_controls_in_scope(built, cnsa2):
    general = " ".join(report_text((built[0] / REPORT).read_bytes()).split())
    assert "Controls this evidence answers" in general
    assert "SOC 2 CC8.1 (source unverified)" in general
    defense = " ".join(report_text((cnsa2[0] / REPORT).read_bytes()).split())
    assert "NIST SP 800-53 CM-4 (source checked 2026-10-07)" in defense
    assert "NIST SP 800-53 CM-3(2) (source checked 2026-10-07)" in defense
    assert "SWFT: no controls mapped" in defense


def test_the_cnsa2_pack_is_signed_with_post_quantum_algorithms_only(cnsa2, keys, release_key):
    out, _ = cnsa2
    crypto = payload(out / PACK_FILE)["predicate"]["crypto"]
    assert crypto["profile"] == "cnsa2"
    assert [s["alg"] for s in crypto["signed_with"]] == ["ml-dsa-87", "lms-sha256-192"]
    for path in out.glob("attestations/*.dsse.json"):
        assert [s["alg"] for s in json.loads(path.read_text())["signatures"]] == ["ml-dsa-87"]
    pq = [load_public(keys[0].public_path), load_public(release_key.public_path)]
    check = verify_pack(out, pq, Policy(distrusted=frozenset({"ecdsa-p384"}), required=frozenset({"ml-dsa-87"})))
    assert check.ok, check.problems
    assert verify_envelope(json.loads((out / PACK_FILE).read_text()), pq,
                           Policy(required=frozenset({"ml-dsa-87", "lms-sha256-192"}))).ok
    assert "Crypto profile: cnsa2" in report_text((out / REPORT).read_bytes())


@pytest.mark.parametrize("name", ["general-hybrid", "eu-dora-hybrid", "us-defense-cnsa2"])
def test_the_three_week13_packs_kept_in_the_repository_verify_and_rebuild(name):
    kept = Path(__file__).resolve().parent.parent / "docs" / "weekly" / "week13-packs"
    keys = [load_public(p) for p in sorted((kept / "keys").glob("*.pub.json"))]
    signing = payload(kept / name / PACK_FILE)["predicate"]["crypto"]["signing"]
    check = verify_pack(kept / name, keys, Policy(required=frozenset(signing)))
    assert check.ok, check.problems
    assert set(check.rebuilt) <= {p.relative_to(kept / name).as_posix() for p in (kept / name).rglob("*") if p.is_file()}
