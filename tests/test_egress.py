import pytest

from changeproof.config import Egress
from changeproof.egress import check_egress

APPROVED = {"allowed": True, "approved_vendors": ["ibm-quantum"]}
CUSTOMER_OK = {"customer_approval_ref": "LTR-7", "ict_register_ref": "ROI-2026-0042", "processing_region": "eea"}

# (classification, data_tier, extra egress settings, allowed?) for the qpu backend, per ADR 003's table.
MATRIX = [
    ("internal", "public", {}, True),
    ("confidential", "synthetic", {}, True),
    ("confidential", "customer-confidential", {}, False),
    ("confidential", "customer-confidential", CUSTOMER_OK, True),
    ("confidential", "customer-confidential", CUSTOMER_OK | {"customer_approval_ref": None}, False),
    ("confidential", "customer-confidential", CUSTOMER_OK | {"ict_register_ref": None}, False),
    ("confidential", "customer-confidential", CUSTOMER_OK | {"processing_region": "other"}, False),
    ("confidential", "customer-confidential", CUSTOMER_OK | {"processing_region": "adequacy"}, True),
    ("restricted", "public", {}, False),
    ("restricted", "customer-confidential", CUSTOMER_OK, False),
]


@pytest.mark.parametrize(("classification", "tier", "extra", "allowed"), MATRIX)
def test_qpu_egress_matrix(classification, tier, extra, allowed):
    egress = Egress(**APPROVED, data_tier=tier, **extra)
    problems = check_egress(classification=classification, backend="qpu", egress=egress, crypto_profile="hybrid")
    assert (problems == []) is allowed, problems


@pytest.mark.parametrize("classification", ["public", "internal", "confidential", "restricted"])
@pytest.mark.parametrize("backend", ["classical", "quantum-sim"])
def test_local_backends_pass_with_egress_denied(classification, backend):
    assert check_egress(classification=classification, backend=backend, egress=Egress(), crypto_profile="hybrid") == []


def test_default_egress_blocks_remote_backend():
    problems = check_egress(classification="internal", backend="qpu", egress=Egress(), crypto_profile="hybrid")
    assert problems == ["optimization.backend 'qpu' sends data off the machine; egress.allowed is false"]


@pytest.mark.parametrize("profile", ["hybrid", "nist-pqc"])
def test_pq_profiles_keep_pq_transport(profile):
    problems = check_egress(
        classification="internal", backend="classical", egress=Egress(require_pq_transport=False), crypto_profile=profile
    )
    assert problems == [f"egress.require_pq_transport must stay true under the {profile} profile"]


def test_classical_legacy_profile_may_drop_pq_transport():
    egress = Egress(require_pq_transport=False)
    assert check_egress(classification="internal", backend="classical", egress=egress, crypto_profile="classical-legacy") == []
