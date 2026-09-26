import pytest

from changeproof.config import Egress
from changeproof.egress import check_egress

APPROVED = {"allowed": True, "approved_vendors": ["ibm-quantum"]}

# (classification, data_tier, extra egress settings, allowed?) for the qpu backend, per ADR 003's table.
MATRIX = [
    ("unclassified", "public", {}, True),
    ("unclassified", "synthetic", {}, True),
    ("unclassified", "customer-unclassified", {}, False),
    ("unclassified", "customer-unclassified", {"customer_approval_ref": "LTR-7"}, True),
    ("cui", "public", {}, False),
    ("cui", "customer-unclassified", {"customer_approval_ref": "LTR-7"}, False),
]


@pytest.mark.parametrize(("classification", "tier", "extra", "allowed"), MATRIX)
def test_qpu_egress_matrix(classification, tier, extra, allowed):
    egress = Egress(**APPROVED, data_tier=tier, **extra)
    problems = check_egress(classification=classification, backend="qpu", egress=egress, crypto_profile="hybrid")
    assert (problems == []) is allowed, problems


@pytest.mark.parametrize("classification", ["unclassified", "cui"])
@pytest.mark.parametrize("backend", ["classical", "quantum-sim"])
def test_local_backends_pass_with_egress_denied(classification, backend):
    assert check_egress(classification=classification, backend=backend, egress=Egress(), crypto_profile="cnsa2") == []


def test_default_egress_blocks_remote_backend():
    problems = check_egress(classification="unclassified", backend="qpu", egress=Egress(), crypto_profile="hybrid")
    assert problems == ["optimization.backend 'qpu' sends data off the machine; egress.allowed is false"]
