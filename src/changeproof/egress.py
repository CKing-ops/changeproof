"""Default-deny egress rules (docs/adr/003-data-egress.md).

Config validation calls these, and the solver interface (Week 10) calls the same function
before any backend flagged remote runs, so there is one rule set, not two. What differs by market
comes from the market profile (docs/adr/004-market-profiles.md).
"""

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from changeproof.config import Egress
    from changeproof.markets import MarketProfile

REMOTE_BACKENDS = frozenset({"qpu"})  # RENAME: SOLVER BACKENDS THAT SEND DATA OFF THE MACHINE
PQ_TRANSPORT_PROFILES = frozenset({"cnsa2", "hybrid", "nist-pqc"})  # RENAME: CRYPTO PROFILES THAT FORBID CLASSICAL-ONLY TLS


# PURPOSE: RETURNS EVERY EGRESS RULE THE SETTINGS BREAK UNDER A MARKET; AN EMPTY LIST MEANS ALLOWED
def check_egress(
    *, market: "MarketProfile", classification: str, backend: str, egress: "Egress", crypto_profile: str
) -> list[str]:
    problems = []  # RENAME: HUMAN-READABLE RULE VIOLATIONS
    if egress.allowed and classification in market.no_egress_classifications:
        problems.append(f"egress.allowed cannot be true when system.classification is {classification}")
    if egress.allowed and egress.data_tier == "customer":
        problems += [
            f"egress.{field} is required for customer data under the {market.name} market"
            for field in market.customer_egress_needs
            if not getattr(egress, field)
        ]
        if market.allowed_regions is not None and egress.processing_region not in market.allowed_regions:
            allowed = " or ".join(sorted(market.allowed_regions))
            problems.append(f"egress.processing_region must be {allowed} for customer data under the {market.name} market")
    if crypto_profile in PQ_TRANSPORT_PROFILES and not egress.require_pq_transport:
        problems.append(f"egress.require_pq_transport must stay true under the {crypto_profile} profile")
    if backend in REMOTE_BACKENDS:
        if not egress.allowed:
            problems.append(f"optimization.backend '{backend}' sends data off the machine; egress.allowed is false")
        elif not egress.approved_vendors:
            problems.append(f"optimization.backend '{backend}' needs at least one egress.approved_vendors entry")
    return problems
