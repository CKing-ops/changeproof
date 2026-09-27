import pytest

from changeproof.config import Egress
from changeproof.egress import check_egress
from changeproof.markets import MARKETS

APPROVED = {"allowed": True, "approved_vendors": ["ibm-quantum"]}
DORA_OK = {"customer_approval_ref": "LTR-7", "ict_register_ref": "ROI-2026-0042", "processing_region": "eea"}

# (market, classification, data_tier, extra egress settings, allowed?) for the qpu backend, per ADR 003's table.
MATRIX = [
    ("general", "internal", "public", {}, True),
    ("general", "confidential", "synthetic", {}, True),
    ("general", "confidential", "customer", {}, False),
    ("general", "confidential", "customer", {"customer_approval_ref": "DPA-12"}, True),
    ("general", "restricted", "public", {}, False),
    ("us-defense", "unclassified", "public", {}, True),
    ("us-defense", "unclassified", "customer", {}, False),
    ("us-defense", "unclassified", "customer", {"customer_approval_ref": "LTR-7"}, True),
    ("us-defense", "cui", "public", {}, False),
    ("us-defense", "cui", "synthetic", {"customer_approval_ref": "LTR-7"}, False),
    ("eu-dora", "internal", "public", {}, True),
    ("eu-dora", "confidential", "synthetic", {}, True),
    ("eu-dora", "confidential", "customer", {}, False),
    ("eu-dora", "confidential", "customer", DORA_OK, True),
    ("eu-dora", "confidential", "customer", DORA_OK | {"customer_approval_ref": None}, False),
    ("eu-dora", "confidential", "customer", DORA_OK | {"ict_register_ref": None}, False),
    ("eu-dora", "confidential", "customer", DORA_OK | {"processing_region": "other"}, False),
    ("eu-dora", "confidential", "customer", DORA_OK | {"processing_region": "adequacy"}, True),
    ("eu-dora", "restricted", "public", {}, False),
    ("eu-dora", "restricted", "customer", DORA_OK, False),
]


# PURPOSE: RUNS THE EGRESS CHECK FOR ONE MARKET WITH THE HYBRID CRYPTO PROFILE
def check(market, classification, egress, backend="qpu", crypto_profile="hybrid"):
    return check_egress(
        market=MARKETS[market], classification=classification, backend=backend, egress=egress, crypto_profile=crypto_profile
    )


@pytest.mark.parametrize(("market", "classification", "tier", "extra", "allowed"), MATRIX)
def test_qpu_egress_matrix(market, classification, tier, extra, allowed):
    problems = check(market, classification, Egress(**APPROVED, data_tier=tier, **extra))
    assert (problems == []) is allowed, problems


def test_region_rule_applies_only_to_dora():
    egress = Egress(**APPROVED, data_tier="customer", customer_approval_ref="DPA-12", processing_region="other")
    assert check("general", "confidential", egress) == []
    assert "processing_region" in " ".join(check("eu-dora", "confidential", egress))


@pytest.mark.parametrize("market", sorted(MARKETS))
@pytest.mark.parametrize("backend", ["classical", "quantum-sim"])
def test_local_backends_pass_with_egress_denied_in_every_market(market, backend):
    for classification in MARKETS[market].classifications:
        assert check(market, classification, Egress(), backend=backend) == []


@pytest.mark.parametrize("market", sorted(MARKETS))
def test_default_egress_blocks_remote_backend(market):
    problems = check(market, MARKETS[market].default_classification, Egress())
    assert problems == ["optimization.backend 'qpu' sends data off the machine; egress.allowed is false"]


@pytest.mark.parametrize("profile", ["cnsa2", "hybrid", "nist-pqc"])
def test_pq_profiles_keep_pq_transport(profile):
    problems = check("general", "internal", Egress(require_pq_transport=False), backend="classical", crypto_profile=profile)
    assert problems == [f"egress.require_pq_transport must stay true under the {profile} profile"]


def test_classical_legacy_profile_may_drop_pq_transport():
    egress = Egress(require_pq_transport=False)
    assert check("general", "internal", egress, backend="classical", crypto_profile="classical-legacy") == []
