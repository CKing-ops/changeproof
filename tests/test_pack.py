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
from changeproof.signer import Policy, digest, generate_key, load_private, load_public

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

_spec = importlib.util.spec_from_file_location("pack_seed", Path(__file__).parent / "fixtures" / "pack" / "seed.py")
_seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_seed)


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    folder = tmp_path_factory.mktemp("keys")
    return [generate_key(alg, folder / alg) for alg in ("ml-dsa-87", "ecdsa-p384")]


@pytest.fixture(scope="module")
def built(tmp_path_factory, keys):
    root = tmp_path_factory.mktemp("pack") / "repo"
    shas = _seed.seed(root)
    out = tmp_path_factory.mktemp("out") / "v1.4"
    build_pack(root, f"{shas['base']}..{shas['co-authored']}", out, [load_private(k.private_path) for k in keys],
               release="v1.4", at=NOW, runner=LocalRunner())
    return out, shas


def trusted(keys):
    return [load_public(k.public_path) for k in keys]


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
        for kind in ("impact", "policy-decision", "behavioral-equivalence")])
    for path in (out / "oscal").iterdir():
        validate_oscal(json.loads(path.read_text()))


def test_the_pack_states_its_crypto_profile_and_the_algorithms_that_signed_it(built, keys):
    out, _ = built
    statement = payload(out / PACK_FILE)
    assert statement["predicateType"] == PREDICATE_TYPES["evidence-pack"]
    crypto = statement["predicate"]["crypto"]
    assert crypto | {"signed_with": None} == {"profile": "hybrid", "signing": ["ml-dsa-87", "ecdsa-p384"],
                                               "release_signing": "lms-sha256-192", "hash": "sha-384", "signed_with": None}
    assert crypto["signed_with"] == [{"alg": load_public(k.public_path).alg, "keyid": k.keyid} for k in keys]
    text = report_text((out / REPORT).read_bytes())
    assert "Crypto profile: hybrid" in text and "ml-dsa-87" in text and "ecdsa-p384" in text


def test_exit_check_the_pack_reconstructs_offline_from_attestations_alone(built, keys, tmp_path):
    out, _ = built
    alone = tmp_path / "alone"
    shutil.copytree(out / "attestations", alone / "attestations")
    shutil.copy(out / PACK_FILE, alone / PACK_FILE)
    check = verify_pack(alone, trusted(keys), Policy())
    assert check.ok, check.problems
    original = {p.relative_to(out).as_posix(): p.read_bytes() for p in [out / REPORT, *(out / "oscal").iterdir()]}
    assert check.rebuilt == original


def test_a_complete_pack_verifies_and_every_file_matches_its_signed_digest(built, keys):
    out, _ = built
    check = verify_pack(out, trusted(keys), Policy(required=frozenset({"ml-dsa-87", "ecdsa-p384"})))
    assert check.ok, check.problems
    subjects = {s["name"]: s["digest"] for s in payload(out / PACK_FILE)["subject"]}
    assert set(subjects) == {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()} - {PACK_FILE}
    assert all(digest((out / name).read_bytes()) == d for name, d in subjects.items())


def test_the_hybrid_pack_still_verifies_when_one_algorithm_is_distrusted(built, keys):
    out, _ = built
    assert verify_pack(out, trusted(keys), Policy(distrusted=frozenset({"ecdsa-p384"}))).ok


@pytest.mark.parametrize("target", ["report", "attestation", "oscal"])
def test_tampering_with_any_file_fails_the_check(built, keys, tmp_path, target):
    out, shas = built
    copy = tmp_path / "copy"
    shutil.copytree(out, copy)
    if target == "report":
        (copy / REPORT).write_bytes((copy / REPORT).read_bytes().replace(b"hybrid", b"hybrlD"))
    elif target == "oscal":
        path = next((copy / "oscal").iterdir())
        path.write_text(path.read_text().replace("not-satisfied", "satisfied"))
    else:
        path = copy / "attestations" / f"02-{shas['co-authored'][:12]}-policy-decision.dsse.json"
        envelope = json.loads(path.read_text())
        body = json.loads(base64.b64decode(envelope["payload"]))
        body["predicate"]["ok"] = True
        envelope["payload"] = base64.b64encode(json.dumps(body).encode()).decode()
        path.write_text(json.dumps(envelope))
    check = verify_pack(copy, trusted(keys), Policy())
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


def test_the_cli_builds_and_verifies_a_pack(built, keys, tmp_path, capsys):
    out, shas = built
    root = tmp_path / "repo"
    _seed.seed(root)
    assert main(["pack", f"{shas['base']}..{shas['assisted']}", "--repo", str(root), "--out", str(tmp_path / "cli"),
                 *[a for k in keys for a in ("--key", str(k.private_path))]]) == 0
    assert json.loads(capsys.readouterr().out)["attestations"] == 3
    assert main(["pack-verify", str(out), *[a for k in keys for a in ("--trust", str(k.public_path))],
                 "--rebuild", str(tmp_path / "rebuilt")]) == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True
    assert (tmp_path / "rebuilt" / REPORT).read_bytes() == (out / REPORT).read_bytes()
    assert main(["pack-verify", str(out), "--trust", str(keys[0].public_path), "--require", "ecdsa-p384"]) == 1


def test_the_sample_pack_kept_in_the_repository_verifies_and_rebuilds():
    sample = Path(__file__).resolve().parent.parent / "docs" / "weekly"
    keys = [load_public(p) for p in sorted((sample / "week12-pack-keys").glob("*.pub.json"))]
    check = verify_pack(sample / "week12-pack", keys, Policy(required=frozenset({"ml-dsa-87", "ecdsa-p384"})))
    assert check.ok, check.problems
