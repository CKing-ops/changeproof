import pytest

from changeproof.adapters.cobol.crypto import classify_call, classify_sql


@pytest.mark.parametrize(("target", "expected"), [
    ("CSNBOWH", ("CSNBOWH", "hash")),
    ("csnbowh", ("CSNBOWH", "hash")),
    ("CSNEOWH", ("CSNBOWH", "hash")),
    ("CSNBOWH1", ("CSNBOWH", "hash")),
    ("CSNDDSG", ("CSNDDSG", "signature-generate")),
    ("CSNFDSG", ("CSNDDSG", "signature-generate")),
    ("CSNDEDH", ("CSNDEDH", "key-agreement")),
    ("CSNBXYZ", ("CSNBXYZ", "unclassified")),
])
def test_icsf_calls_are_classified(target, expected):
    assert classify_call(target) == expected


@pytest.mark.parametrize("target", ["PAYAUDIT", "CEE3ABD", "MVSWAIT", "CSN"])
def test_ordinary_calls_are_not_crypto(target):
    assert classify_call(target) is None


def test_sql_crypto_functions_are_found():
    sql = "SELECT HASH_SHA256(NAME), ENCRYPT_TDES(:PAN, :PW) INTO :A, :B FROM T"
    assert classify_sql(sql) == [("HASH_SHA256", "hash"), ("ENCRYPT_TDES", "symmetric-encrypt")]


def test_column_names_that_contain_function_names_are_not_matched():
    assert classify_sql("SELECT HASH_KEY, CARD_HASH FROM T WHERE X-HASH(1) = 2") == []


@pytest.fixture(scope="module")
def pkasign():
    from pathlib import Path

    from changeproof.adapters.cobol import CobolAdapter

    root = Path(__file__).resolve().parent / "fixtures" / "cobol"
    module = CobolAdapter(copybook_dirs=["copy"]).parse(root / "src" / "PKASIGN.cbl", root)
    return {e.attributes["service"]: e for e in module.entities if e.kind == "crypto-call"}, \
        {e.id: e for e in module.entities}


def test_algorithm_and_key_size_come_from_values_the_call_is_given(pkasign):
    calls, entities = pkasign
    build = calls["CSNDPKB"].attributes
    assert (build["algorithm"], build["key_bits"], build["quantum_vulnerable"]) == ("rsa", 2048, True)
    sources = [entities[i] for i in build["algorithm_from"]]
    assert [(s.name, s.provenance.line) for s in sources] == [("WS-KEY-TYPE", 10), ("WS-MODULUS-BITS", 12)]
    assert build["using"][:3] == ["WS-RC", "WS-REASON", "WS-RULE-COUNT"]


def test_a_moved_literal_names_the_algorithm(pkasign):
    calls, entities = pkasign
    sign = calls["CSNDDSG"].attributes
    assert (sign["algorithm"], sign["quantum_vulnerable"]) == ("ecc", True)
    assert entities[sign["algorithm_from"][0]].provenance.line == 23


def test_hashes_are_not_quantum_vulnerable(pkasign):
    calls, _ = pkasign
    assert (calls["CSNBOWH"].attributes["algorithm"], calls["CSNBOWH"].attributes["quantum_vulnerable"]) == \
        ("sha-256", False)


def test_a_public_key_call_with_no_readable_algorithm_is_undetermined(pkasign):
    calls, _ = pkasign
    found = calls["CSNDPKE"].attributes
    assert found["algorithm"] is None and found["quantum_vulnerable"] is None and found["algorithm_from"] == []
