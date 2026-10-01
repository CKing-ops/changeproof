"""Market profiles (docs/adr/004-market-profiles.md).

A profile holds the only rules that differ between markets: how systems are classified, which
classes may never send data out, what customer-data egress must cite, and which frameworks the
evidence is mapped to. The engine, schemas and adapters are the same for every market.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class MarketProfile:
    name: str
    classifications: tuple[str, ...]
    default_classification: str
    no_egress_classifications: frozenset[str]
    customer_egress_needs: tuple[str, ...]  # egress fields that must be set before customer data leaves
    allowed_regions: frozenset[str] | None  # None means the profile has no data-residency rule
    frameworks: tuple[str, ...]


GENERAL = MarketProfile(
    name="general",
    classifications=("public", "internal", "confidential", "restricted"),
    default_classification="internal",
    no_egress_classifications=frozenset({"restricted"}),
    customer_egress_needs=("customer_approval_ref",),
    allowed_regions=None,
    frameworks=("soc2", "iso-27001"),
)

US_DEFENSE = MarketProfile(
    name="us-defense",
    classifications=("unclassified", "cui"),
    default_classification="unclassified",
    no_egress_classifications=frozenset({"cui"}),
    customer_egress_needs=("customer_approval_ref",),
    allowed_regions=None,
    frameworks=("nist-ssdf", "nist-800-53-cm", "nist-800-53-sc", "swft", "cnsa2"),
)

EU_DORA = MarketProfile(
    name="eu-dora",
    classifications=("public", "internal", "confidential", "restricted"),
    default_classification="internal",
    no_egress_classifications=frozenset({"restricted"}),
    customer_egress_needs=("customer_approval_ref", "ict_register_ref"),  # DORA Art. 28(3) register, unverified
    allowed_regions=frozenset({"eea", "adequacy"}),  # DORA Art. 30, GDPR Chapter V, unverified
    frameworks=("dora", "dora-rts-ict-risk", "ecb-itrq", "eu-pqc-roadmap", "gdpr"),
)

MARKETS = {p.name: p for p in (GENERAL, US_DEFENSE, EU_DORA)}  # RENAME: MARKET NAME TO PROFILE
DEFAULT_MARKET = GENERAL.name  # RENAME: MARKET USED WHEN THE CONFIG NAMES NONE
