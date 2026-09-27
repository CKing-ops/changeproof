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
