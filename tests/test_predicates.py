import copy
import json
from pathlib import Path

import jsonschema
import pytest

from changeproof.predicates import PREDICATE_TYPES, statement, validate_predicate

FIXTURES = Path(__file__).parent / "fixtures" / "predicates"


def load(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text())


@pytest.mark.parametrize("name", ["impact", "behavioral-equivalence", "crypto-inventory"])
def test_example_predicates_validate(name):
    validate_predicate(PREDICATE_TYPES[name], load(name))


def test_predicate_types_are_versioned_uris():
    assert PREDICATE_TYPES == {
        "impact": "urn:changeproof:predicate:impact:v0.1",
        "behavioral-equivalence": "urn:changeproof:predicate:behavioral-equivalence:v0.1",
        "crypto-inventory": "urn:changeproof:predicate:crypto-inventory:v0.1",
        "release": "urn:changeproof:predicate:release:v0.1",
        "policy-decision": "urn:changeproof:predicate:policy-decision:v0.1",
        "evidence-pack": "urn:changeproof:predicate:evidence-pack:v0.1",
    }


@pytest.mark.parametrize(
    ("name", "path"),
    [
        ("impact", ["changed", 0]),
        ("impact", ["impacted", 0]),
        ("impact", ["impacted", 0, "via", 0]),
        ("behavioral-equivalence", ["tests", 0, "target"]),
        ("crypto-inventory", ["findings", 0]),
    ],
)
def test_every_fact_requires_provenance(name, path):
    doc = copy.deepcopy(load(name))
    node = doc
    for key in path:
        node = node[key]
    del node["provenance"]
    with pytest.raises(jsonschema.ValidationError, match="provenance"):
        validate_predicate(PREDICATE_TYPES[name], doc)


def test_absolute_provenance_paths_are_rejected():
    doc = load("crypto-inventory")
    doc["findings"][0]["provenance"]["file"] = "/home/dev/PAYSIGN.cbl"
    with pytest.raises(jsonschema.ValidationError):
        validate_predicate(PREDICATE_TYPES["crypto-inventory"], doc)


def test_unknown_predicate_type_is_rejected():
    with pytest.raises(KeyError, match="unknown predicate type"):
        validate_predicate("urn:changeproof:predicate:impact:v9", load("impact"))


def test_statement_wraps_predicate_in_in_toto_v1():
    subject = {"name": "corpus/carddemo/app/cbl/CBACT01C.cbl", "digest": {"sha384": "ab12"}}
    stmt = statement([subject], PREDICATE_TYPES["impact"], load("impact"))
    assert stmt["_type"] == "https://in-toto.io/Statement/v1"
    assert stmt["subject"] == [subject]
    assert stmt["predicateType"] == "urn:changeproof:predicate:impact:v0.1"


def test_statement_refuses_invalid_predicate():
    doc = load("impact")
    del doc["engine"]
    with pytest.raises(jsonschema.ValidationError):
        statement([{"name": "x", "digest": {"sha384": "ab"}}], PREDICATE_TYPES["impact"], doc)


def test_statement_needs_a_subject():
    with pytest.raises(ValueError, match="subject"):
        statement([], PREDICATE_TYPES["impact"], load("impact"))
