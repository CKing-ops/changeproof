"""One combined, signed record per change, with the four separate attestations kept as a choice."""

import base64
import importlib.util
import io
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from pypdf import PdfReader

from changeproof.characterize import LocalRunner
from changeproof.cli import main
from changeproof.pack import PACK_FILE, REPORT, build_pack, verify_pack, write_records
from changeproof.predicates import PREDICATE_TYPES, validate_predicate
from changeproof.signer import Policy, generate_key, load_private, load_public, verify_envelope

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
SEPARATE = ("impact", "policy-decision", "behavioral-equivalence", "full-suite")

_spec = importlib.util.spec_from_file_location("pack_seed", Path(__file__).parent / "fixtures" / "pack" / "seed.py")
_seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_seed)


@pytest.fixture(scope="module")
def keys(tmp_path_factory):
    folder = tmp_path_factory.mktemp("keys")
    return [generate_key(alg, folder / alg) for alg in ("ml-dsa-87", "ecdsa-p384")]


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("record") / "repo"
    return root, _seed.seed(root)


@pytest.fixture(scope="module")
def packs(tmp_path_factory, repo, keys):
    root, shas = repo
    found = {}
    for layout in ("combined", "separate"):
        out = tmp_path_factory.mktemp(layout) / "v1.4"
        build_pack(root, f"{shas['base']}..{shas['co-authored']}", out, [load_private(k.private_path) for k in keys],
                   release="v1.4", at=NOW, runner=LocalRunner(), layout=layout)
        found[layout] = out
    return found


def payload(path: Path) -> dict:
    return json.loads(base64.b64decode(json.loads(path.read_text())["payload"]))


def report_text(data: bytes) -> str:
    return "\n".join(page.extract_text() for page in PdfReader(io.BytesIO(data)).pages)


def test_the_combined_record_holds_all_four_parts_of_a_change_in_one_signed_statement(repo, keys, tmp_path):
    root, shas = repo
    listed, _ = write_records(root, shas["co-authored"], tmp_path, [load_private(k.private_path) for k in keys],
                           at=NOW, runner=LocalRunner())
    assert [item["path"] for item in listed] == [f"01-{shas['co-authored'][:12]}-change-record.dsse.json"]
    envelope = json.loads((tmp_path / listed[0]["path"]).read_text())
    assert verify_envelope(envelope, [load_public(k.public_path) for k in keys],
                           Policy(required=frozenset({"ml-dsa-87", "ecdsa-p384"}))).ok
    found = payload(tmp_path / listed[0]["path"])
    assert found["predicateType"] == PREDICATE_TYPES["change-record"]
    assert found["subject"] == [{"name": found["predicate"]["change"]["repository"],
                                 "digest": {"gitCommit": shas["co-authored"]}}]
    record = found["predicate"]
    assert record["change"]["head"] == shas["co-authored"]
    assert record["behavioral_equivalence"]["scope"] == "outside-impact-set"
    assert record["full_suite"]["scope"] == "full-suite"
    assert not record["policy_decision"]["ok"]
    validate_predicate(PREDICATE_TYPES["impact"], record["impact"])


def test_the_separate_layout_still_writes_one_attestation_per_part(repo, keys, tmp_path):
    root, shas = repo
    listed, _ = write_records(root, shas["co-authored"], tmp_path, [load_private(k.private_path) for k in keys],
                           at=NOW, runner=LocalRunner(), layout="separate")
    assert [item["path"] for item in listed] == [f"01-{shas['co-authored'][:12]}-{kind}.dsse.json" for kind in SEPARATE]


def test_both_layouts_hold_the_same_evidence_and_give_the_same_report(packs):
    combined, separate = packs["combined"], packs["separate"]
    assert sorted(p.name for p in (combined / "attestations").iterdir()) == sorted(
        f"{p.name.rsplit('-', 1)[0]}-change-record.dsse.json" for p in (separate / "attestations").iterdir()
        if p.name.endswith("-impact.dsse.json"))
    for name in sorted(p.name for p in (combined / "attestations").iterdir()):
        record = payload(combined / "attestations" / name)["predicate"]
        stem = name.removesuffix("-change-record.dsse.json")
        for kind, key in zip(SEPARATE, ("impact", "policy_decision", "behavioral_equivalence", "full_suite")):
            assert record[key] == payload(separate / "attestations" / f"{stem}-{kind}.dsse.json")["predicate"]
    assert report_text((combined / REPORT).read_bytes()).split("\nAttestations")[0] == \
        report_text((separate / REPORT).read_bytes()).split("\nAttestations")[0]
    oscal = sorted(p.name for p in (separate / "oscal").iterdir())
    assert oscal and oscal == sorted(p.name for p in (combined / "oscal").iterdir())
    assert all((combined / "oscal" / n).read_bytes() == (separate / "oscal" / n).read_bytes() for n in oscal)


def test_a_combined_pack_verifies_and_rebuilds_offline(packs, keys):
    check = verify_pack(packs["combined"], [load_public(k.public_path) for k in keys],
                        Policy(required=frozenset({"ml-dsa-87", "ecdsa-p384"})))
    assert check.ok, check.problems
    assert {item["predicate_type"] for item in payload(packs["combined"] / PACK_FILE)["predicate"]["attestations"]} \
        == {PREDICATE_TYPES["change-record"]}


def test_the_record_command_writes_the_layout_chosen_and_combined_is_the_default(repo, keys, tmp_path):
    root, shas = repo
    signing = [arg for k in keys for arg in ("--key", str(k.private_path))]
    assert main(["record", shas["assisted"], "--repo", str(root), "--out", str(tmp_path / "one"), *signing]) == 0
    assert [p.name for p in (tmp_path / "one").iterdir()] == [f"01-{shas['assisted'][:12]}-change-record.dsse.json"]
    assert main(["record", shas["assisted"], "--repo", str(root), "--out", str(tmp_path / "four"),
                 "--layout", "separate", *signing]) == 0
    assert sorted(p.name for p in (tmp_path / "four").iterdir()) == sorted(
        f"01-{shas['assisted'][:12]}-{kind}.dsse.json" for kind in SEPARATE)
