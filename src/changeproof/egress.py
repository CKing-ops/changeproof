"""Default-deny egress rules (docs/adr/003-data-egress.md).

Config validation calls these today. The Week 10 solver interface will call the same function
before any backend flagged remote runs, so there is one rule set, not two.
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from changeproof.config import Egress

NO_EGRESS_CLASSIFICATIONS = frozenset({"restricted"})  # RENAME: SYSTEM CLASSES THAT MAY NEVER SEND DATA OUT
ALLOWED_REGIONS = frozenset({"eea", "adequacy"})  # RENAME: VENDOR PROCESSING REGIONS OK FOR CUSTOMER DATA
REMOTE_BACKENDS = frozenset({"qpu"})  # RENAME: SOLVER BACKENDS THAT SEND DATA OFF THE MACHINE
PQ_TRANSPORT_PROFILES = frozenset({"hybrid", "nist-pqc"})  # RENAME: CRYPTO PROFILES THAT FORBID CLASSICAL-ONLY TLS


# PURPOSE: RETURNS EVERY EGRESS RULE THE SETTINGS BREAK; AN EMPTY LIST MEANS ALLOWED
def check_egress(*, classification: str, backend: str, egress: "Egress", crypto_profile: str) -> list[str]:
    problems = []  # RENAME: HUMAN-READABLE RULE VIOLATIONS
    if egress.allowed and classification in NO_EGRESS_CLASSIFICATIONS:
        problems.append(f"egress.allowed cannot be true when system.classification is {classification}")
    if egress.allowed and egress.data_tier == "customer-confidential":
        if not egress.customer_approval_ref:
            problems.append("egress.customer_approval_ref is required for customer-confidential data")
        if not egress.ict_register_ref:
            problems.append("egress.ict_register_ref is required for customer-confidential data "
                            "(vendor must be in the DORA register of information)")
        if egress.processing_region not in ALLOWED_REGIONS:
            problems.append("egress.processing_region must be eea or adequacy for customer-confidential data")
    if crypto_profile in PQ_TRANSPORT_PROFILES and not egress.require_pq_transport:
        problems.append(f"egress.require_pq_transport must stay true under the {crypto_profile} profile")
    if backend in REMOTE_BACKENDS:
        if not egress.allowed:
            problems.append(f"optimization.backend '{backend}' sends data off the machine; egress.allowed is false")
        elif not egress.approved_vendors:
            problems.append(f"optimization.backend '{backend}' needs at least one egress.approved_vendors entry")
    return problems
