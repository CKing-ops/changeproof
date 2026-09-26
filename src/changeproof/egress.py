"""Default-deny egress rules (docs/adr/003-data-egress.md).

Config validation calls these today. The Week 10 solver interface will call the same function
before any backend flagged remote runs, so there is one rule set, not two.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from changeproof.config import Egress

REMOTE_BACKENDS = frozenset({"qpu"})  # RENAME: SOLVER BACKENDS THAT SEND DATA OFF THE MACHINE
PQ_TRANSPORT_PROFILES = frozenset({"cnsa2"})  # RENAME: CRYPTO PROFILES THAT FORBID CLASSICAL-ONLY TLS


# PURPOSE: RETURNS EVERY EGRESS RULE THE SETTINGS BREAK; AN EMPTY LIST MEANS ALLOWED
def check_egress(*, classification: str, backend: str, egress: "Egress", crypto_profile: str) -> list[str]:
    problems = []  # RENAME: HUMAN-READABLE RULE VIOLATIONS
    if egress.allowed and classification != "unclassified":
        problems.append(f"egress.allowed cannot be true when system.classification is {classification}")
    if egress.allowed and egress.data_tier == "customer-unclassified" and not egress.customer_approval_ref:
        problems.append("egress.customer_approval_ref is required for customer-unclassified data")
    if crypto_profile in PQ_TRANSPORT_PROFILES and not egress.require_pq_transport:
        problems.append(f"egress.require_pq_transport must stay true under the {crypto_profile} profile")
    if backend in REMOTE_BACKENDS:
        if not egress.allowed:
            problems.append(f"optimization.backend '{backend}' sends data off the machine; egress.allowed is false")
        elif not egress.approved_vendors:
            problems.append(f"optimization.backend '{backend}' needs at least one egress.approved_vendors entry")
    return problems
