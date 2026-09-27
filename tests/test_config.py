import copy
import json
from pathlib import Path

import jsonschema
import pytest
import yaml
from pydantic import ValidationError

from changeproof.config import Config, load_config

ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = ROOT / "docs" / "examples"
EXAMPLE = EXAMPLES / "changeproof.yaml"
MARKET_EXAMPLES = {"general": EXAMPLE, "us-defense": EXAMPLES / "us-defense.yaml", "eu-dora": EXAMPLES / "eu-dora.yaml"}
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
    assert config.market == "general"
    assert config.components[0].language == "cobol"
    assert config.version == "0.1"


@pytest.mark.parametrize("market", sorted(MARKET_EXAMPLES))
def test_each_market_sample_validates(market):
    path = MARKET_EXAMPLES[market]
    assert load_config(path).market == market
    jsonschema.validate(yaml.safe_load(path.read_text()), json.loads(SCHEMA.read_text()))


def test_market_defaults_to_general(raw):
    del raw["market"]
    assert Config.model_validate(raw).market == "general"


def test_unknown_market_is_rejected(raw):
    raw["market"] = "mars"
    with pytest.raises(ValidationError, match="market"):
        Config.model_validate(raw)


@pytest.mark.parametrize(("market", "default"), [("general", "internal"), ("us-defense", "unclassified"), ("eu-dora", "internal")])
def test_default_classification_follows_the_market(raw, market, default):
    del raw["system"]["classification"]
    raw["market"] = market
    assert Config.model_validate(raw).system.classification == default


@pytest.mark.parametrize(("market", "classification"), [("general", "cui"), ("eu-dora", "cui"), ("us-defense", "confidential")])
def test_classification_must_belong_to_the_market(raw, market, classification):
    raw["market"] = market
    raw["system"]["classification"] = classification
    with pytest.raises(ValidationError, match=f"not a {market} classification"):
        Config.model_validate(raw)


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
    raw["system"]["clasification"] = "internal"
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


def test_customer_data_egress_needs_approval(raw):
    data = with_changes(
        raw,
        optimization={"backend": "qpu"},
        egress={"allowed": True, "data_tier": "customer", "approved_vendors": ["ibm-quantum"]},
    )
    with pytest.raises(ValidationError, match="customer_approval_ref"):
        Config.model_validate(data)
    data["egress"]["customer_approval_ref"] = "DPA-12"
    assert Config.model_validate(data).egress.customer_approval_ref == "DPA-12"


def test_dora_customer_data_egress_needs_approval_register_entry_and_eu_processing(raw):
    data = with_changes(
        raw,
        optimization={"backend": "qpu"},
        egress={"allowed": True, "data_tier": "customer", "approved_vendors": ["ibm-quantum"]},
    )
    data["market"] = "eu-dora"
    with pytest.raises(ValidationError) as err:
        Config.model_validate(data)
    for field in ("customer_approval_ref", "ict_register_ref", "processing_region"):
        assert field in str(err.value)
    data["egress"] |= {"customer_approval_ref": "LTR-7", "ict_register_ref": "ROI-2026-0042", "processing_region": "eea"}
    assert Config.model_validate(data).egress.ict_register_ref == "ROI-2026-0042"


def test_restricted_system_can_never_allow_egress(raw):
    data = with_changes(
        raw,
        system={"classification": "restricted"},
        egress={"allowed": True, "data_tier": "public", "approved_vendors": ["ibm-quantum"]},
    )
    with pytest.raises(ValidationError, match="restricted"):
        Config.model_validate(data)


def test_local_backends_never_need_egress(raw):
    for backend in ("classical", "quantum-sim"):
        data = with_changes(raw, system={"classification": "restricted"}, optimization={"backend": backend})
        assert Config.model_validate(data).optimization.backend == backend


def test_hybrid_profile_requires_pq_transport(raw):
    data = with_changes(raw, egress={"require_pq_transport": False})
    with pytest.raises(ValidationError, match="require_pq_transport"):
        Config.model_validate(data)


def test_old_market_specific_data_tiers_are_rejected(raw):
    for tier in ("customer-unclassified", "customer-confidential"):
        with pytest.raises(ValidationError):
            Config.model_validate(with_changes(raw, egress={"data_tier": tier}))


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
