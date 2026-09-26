import json
from functools import cache
from importlib.resources import files
from typing import Any

import jsonschema
from referencing import Registry, Resource

STATEMENT_TYPE = "https://in-toto.io/Statement/v1"
PREDICATE_NAMES = ("impact", "behavioral-equivalence", "crypto-inventory")  # RENAME: DRAFT PREDICATES SHIPPED IN V0.1
PREDICATE_TYPES = {name: f"urn:changeproof:predicate:{name}:v0.1" for name in PREDICATE_NAMES}


# PURPOSE: LOADS EVERY BUNDLED SCHEMA AND INDEXES IT BY ITS $ID SO $REFS RESOLVE OFFLINE
@cache
def schema_registry() -> Registry:
    resources = [
        Resource.from_contents(json.loads(path.read_text(encoding="utf-8")))
        for path in files("changeproof.predicates").joinpath("schemas").iterdir()
        if path.name.endswith(".json")
    ]
    return Registry().with_resources((r.id(), r) for r in resources)


# PURPOSE: CHECKS A PREDICATE BODY AGAINST THE SCHEMA FOR ITS TYPE URI
def validate_predicate(predicate_type: str, predicate: dict[str, Any]) -> None:
    registry = schema_registry()
    if predicate_type not in registry:
        raise KeyError(f"unknown predicate type {predicate_type}")
    schema = registry.contents(predicate_type)
    jsonschema.Draft202012Validator(schema, registry=registry).validate(predicate)


# PURPOSE: WRAPS A VALIDATED PREDICATE IN AN IN-TOTO V1 STATEMENT, READY FOR SIGNING
def statement(subjects: list[dict[str, Any]], predicate_type: str, predicate: dict[str, Any]) -> dict[str, Any]:
    if not subjects:
        raise ValueError("an in-toto statement needs at least one subject")
    validate_predicate(predicate_type, predicate)
    return {"_type": STATEMENT_TYPE, "subject": subjects, "predicateType": predicate_type, "predicate": predicate}
