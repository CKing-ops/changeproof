import copy
import json
from pathlib import Path

import jsonschema
import pytest
import yaml
from pydantic import ValidationError

from changeproof.config import Config, load_config

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "docs" / "examples" / "changeproof.yaml"
SCHEMA = ROOT / "src" / "changeproof" / "schema" / "changeproof.schema.json"


@pytest.fixture
def raw() -> dict:
    return yaml.safe_load(EXAMPLE.read_text())


def with_changes(raw: dict, **sections) -> dict:
    data = copy.deepcopy(raw)
    for section, values in sections.items():
        data[section] = {**data.get(section, {}), **values}
    return data


def test_roadmap_sample_config_validates():
    config = load_config(EXAMPLE)
    assert config.system.name == "logistics-core"
    assert config.components[0].language == "cobol"
    assert config.version == "0.1"


def test_committed_json_schema_matches_models():
    assert json.loads(SCHEMA.read_text()) == Config.model_json_schema()


def test_sample_config_validates_against_json_schema(raw):
    jsonschema.validate(raw, json.loads(SCHEMA.read_text()))


def test_egress_is_denied_when_section_is_missing(raw):
    del raw["egress"]
    config = Config.model_validate(raw)
    assert config.egress.allowed is False
    assert config.egress.require_pq_transport is True


def test_unknown_keys_are_rejected(raw):
    raw["system"]["clasification"] = "unclassified"
    with pytest.raises(ValidationError, match="clasification"):
        Config.model_validate(raw)


def test_qpu_backend_fails_while_egress_is_denied(raw):
    data = with_changes(raw, optimization={"backend": "qpu"})
    with pytest.raises(ValidationError, match="egress.allowed"):
        Config.model_validate(data)


def test_qpu_backend_needs_an_approved_vendor(raw):
    data = with_changes(raw, optimization={"backend": "qpu"}, egress={"allowed": True})
    with pytest.raises(ValidationError, match="approved_vendors"):
        Config.model_validate(data)


def test_qpu_backend_allowed_for_public_data_with_vendor(raw):
    data = with_changes(
        raw,
        optimization={"backend": "qpu"},
        egress={"allowed": True, "data_tier": "public", "approved_vendors": ["ibm-quantum"]},
    )
    assert Config.model_validate(data).optimization.backend == "qpu"


def test_customer_data_egress_needs_written_approval(raw):
    data = with_changes(
        raw,
        optimization={"backend": "qpu"},
        egress={"allowed": True, "data_tier": "customer-unclassified", "approved_vendors": ["ibm-quantum"]},
    )
    with pytest.raises(ValidationError, match="customer_approval_ref"):
        Config.model_validate(data)
    data["egress"]["customer_approval_ref"] = "LETTER-2026-014"
    assert Config.model_validate(data).egress.customer_approval_ref == "LETTER-2026-014"


def test_cui_system_can_never_allow_egress(raw):
    data = with_changes(
        raw,
        system={"classification": "cui"},
        egress={"allowed": True, "data_tier": "public", "approved_vendors": ["ibm-quantum"]},
    )
    with pytest.raises(ValidationError, match="cui"):
        Config.model_validate(data)


def test_local_backends_never_need_egress(raw):
    for backend in ("classical", "quantum-sim"):
        data = with_changes(raw, system={"classification": "cui"}, optimization={"backend": backend})
        assert Config.model_validate(data).optimization.backend == backend


def test_cnsa2_profile_requires_pq_transport(raw):
    data = with_changes(raw, egress={"require_pq_transport": False})
    with pytest.raises(ValidationError, match="require_pq_transport"):
        Config.model_validate(data)


def test_crypto_algorithms_are_identifiers_not_a_closed_list(raw):
    data = with_changes(raw, crypto={"signing": ["slh-dsa-shake-256s"], "profile": "nist-pqc"})
    assert Config.model_validate(data).crypto.signing == ["slh-dsa-shake-256s"]


def test_crypto_algorithm_ids_must_be_well_formed(raw):
    data = with_changes(raw, crypto={"hash": "SHA 384"})
    with pytest.raises(ValidationError, match="hash"):
        Config.model_validate(data)


def test_crypto_section_is_required(raw):
    del raw["crypto"]
    with pytest.raises(ValidationError, match="crypto"):
        Config.model_validate(raw)


def test_unsupported_version_is_rejected(raw):
    raw["version"] = 0.2
    with pytest.raises(ValidationError, match="version"):
        Config.model_validate(raw)
