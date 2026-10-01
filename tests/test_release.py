"""Week 6: the engine's own release artifacts signed per its release_signing algorithm."""

from datetime import UTC, datetime

from changeproof.predicates import PREDICATE_TYPES
from changeproof.release import check_subjects, release_statement
from changeproof.signer import Policy, digest, generate_key, load_private, load_public, sign_envelope, verify_envelope

NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def artifacts(root):
    (root / "dist").mkdir()
    (root / "dist" / "changeproof-0.1.0-py3-none-any.whl").write_bytes(b"wheel bytes")
    (root / "dist" / "changeproof-0.1.0.tar.gz").write_bytes(b"sdist bytes")
    return sorted((root / "dist").iterdir())


def test_release_statement_names_each_artifact_with_its_sha_384(tmp_path):
    paths = artifacts(tmp_path)
    found = release_statement(paths, tmp_path, "0.1.0")
    assert found["predicateType"] == PREDICATE_TYPES["release"]
    assert found["subject"] == [{"name": "dist/changeproof-0.1.0-py3-none-any.whl", "digest": digest(b"wheel bytes")},
                                {"name": "dist/changeproof-0.1.0.tar.gz", "digest": digest(b"sdist bytes")}]
    assert found["predicate"]["product"] == {"name": "changeproof", "version": "0.1.0"}


def test_a_changed_artifact_fails_the_subject_check(tmp_path):
    paths = artifacts(tmp_path)
    key = generate_key("lms-sha256-192", tmp_path / "release")
    envelope = sign_envelope(release_statement(paths, tmp_path, "0.1.0"), [load_private(key.private_path)], NOW)
    assert verify_envelope(envelope, [load_public(key.public_path)], Policy()).ok
    assert check_subjects(envelope, tmp_path) == []
    paths[1].write_bytes(b"sdist bytes, swapped")
    assert check_subjects(envelope, tmp_path) == ["dist/changeproof-0.1.0.tar.gz: digest differs"]
    paths[0].unlink()
    assert "dist/changeproof-0.1.0-py3-none-any.whl: missing" in check_subjects(envelope, tmp_path)
