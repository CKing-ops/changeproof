from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, WithJsonSchema, model_validator

from changeproof.egress import check_egress

Identifier = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")]
AlgorithmId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9-]*$")]

# YAML reads `version: 0.1` as a float; accept both spellings.
SchemaVersion = Annotated[
    Literal["0.1"],
    BeforeValidator(lambda v: str(v) if isinstance(v, float) else v),
    WithJsonSchema({"enum": ["0.1", 0.1]}),
]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


# Bank-style information classification, as most EU financial entities label their data.
class Classification(StrEnum):
    PUBLIC = "public"
    INTERNAL = "internal"
    CONFIDENTIAL = "confidential"
    RESTRICTED = "restricted"


class Criticality(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class DataTier(StrEnum):
    PUBLIC = "public"
    SYNTHETIC = "synthetic"
    CUSTOMER_CONFIDENTIAL = "customer-confidential"


# Where a vendor processes data: inside the EEA, in a country with a GDPR adequacy decision, or elsewhere.
class ProcessingRegion(StrEnum):
    EEA = "eea"
    ADEQUACY = "adequacy"
    OTHER = "other"


class EvidenceKind(StrEnum):
    IMPACT = "impact"
    BEHAVIORAL_EQUIVALENCE = "behavioral-equivalence"
    CRYPTO_INVENTORY = "crypto-inventory"


class OutputFormat(StrEnum):
    IN_TOTO = "in-toto"
    OSCAL = "oscal"
    CYCLONEDX_CBOM = "cyclonedx-cbom"
    PDF = "pdf"


class System(Strict):
    name: str = Field(min_length=1)
    owner: str = Field(min_length=1)
    classification: Classification = Classification.INTERNAL


class Component(Strict):
    id: Identifier
    path: str = Field(min_length=1)
    language: Identifier  # adapter key; adapters are pluggable, so this is not an enum
    criticality: Criticality = Criticality.MEDIUM
    data_stores: list[str] = []
    relied_on_by: list[str] = []


class Evidence(Strict):
    produce: list[EvidenceKind] = list(EvidenceKind)
    outputs: list[OutputFormat] = [OutputFormat.IN_TOTO]


# Algorithm IDs are opaque here. Only the signer interface knows what they mean (ADR 002).
class Crypto(Strict):
    profile: Identifier
    signing: list[AlgorithmId] = Field(min_length=1)
    release_signing: AlgorithmId
    hash: AlgorithmId


class Optimization(Strict):
    backend: Identifier = "classical"


class Egress(Strict):
    allowed: bool = False
    data_tier: DataTier = DataTier.PUBLIC
    approved_vendors: list[Identifier] = []
    customer_approval_ref: str | None = None
    ict_register_ref: str | None = None  # entry in the DORA register of information (Art. 28(3))
    processing_region: ProcessingRegion | None = None
    require_pq_transport: bool = True


class PolicyRule(Strict):
    rule: Identifier


class Config(Strict):
    version: SchemaVersion
    system: System
    components: list[Component] = []
    evidence: Evidence = Evidence()
    crypto: Crypto
    optimization: Optimization = Optimization()
    egress: Egress = Egress()
    policy: list[PolicyRule] = []
    frameworks: list[Identifier] = []

    # PURPOSE: APPLIES THE DEFAULT-DENY EGRESS RULES FROM ADR 003 TO THE WHOLE CONFIG
    @model_validator(mode="after")
    def enforce_egress(self) -> "Config":
        problems = check_egress(  # RENAME: EGRESS RULE VIOLATIONS
            classification=self.system.classification,
            backend=self.optimization.backend,
            egress=self.egress,
            crypto_profile=self.crypto.profile,
        )
        if problems:
            raise ValueError("; ".join(problems))
        return self


# PURPOSE: READS A CHANGEPROOF.YAML FILE AND RETURNS THE VALIDATED CONFIG
def load_config(path: Path) -> Config:
    return Config.model_validate(yaml.safe_load(Path(path).read_text(encoding="utf-8")))
