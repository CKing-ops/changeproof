"""Test search that reaches what one-field-at-a-time changes miss, measured on the bank simulation's misses (ADR 015)."""

import pytest

from changeproof.banksim import BANKS, catalogue, render
from changeproof.characterize import LocalRunner, characterize, replay

BANK = next(b for b in BANKS if b.id == "copperline")


# PURPOSE: A FRESH COPY OF THE BANK'S PROGRAMS WITH THE NAMED CATALOGUE CHANGES APPLIED IN ORDER
def estate(root, *changes):
    render(BANK, root)
    by_id = {c.id: c for c in catalogue(BANK)}
    for change in map(by_id.get, changes):
        path = root / change.path
        path.write_text(path.read_text().replace(change.old, change.new, 1))
    return root


# PURPOSE: CHARACTERIZES ONE PROGRAM OF AN ESTATE
def suite_of(root, program):
    return characterize(root / "src" / f"{program}.cbl", root, LocalRunner())


@pytest.fixture(scope="module")
def fee_suite(tmp_path_factory):
    return suite_of(estate(tmp_path_factory.mktemp("fee")), "FEEASSES")


@pytest.fixture(scope="module")
def posting_suite(tmp_path_factory):
    return suite_of(estate(tmp_path_factory.mktemp("post")), "POSTTXN")


def test_a_threshold_is_tried_below_on_and_above_on_the_path_that_compares_it(fee_suite):
    retail = {t["input"]["LK-AVG-BALANCE"] for t in fee_suite["tests"] if t["input"]["LK-SEGMENT"] == "R"}
    assert {"2499.99", "2500.00", "2500.01"} <= retail


def test_a_waiver_made_strict_is_caught(fee_suite, tmp_path):
    assert replay(fee_suite, estate(tmp_path, "fee-waiver-strict"), LocalRunner())


def test_a_slipped_charge_is_caught_after_the_free_count_became_inclusive(tmp_path):
    suite = suite_of(estate(tmp_path / "base", "fee-free-txns-inclusive"), "FEEASSES")
    assert replay(suite, estate(tmp_path / "head", "fee-free-txns-inclusive", "fee-per-txn-slip"), LocalRunner())


def test_a_batch_job_reaches_an_outcome_that_needs_several_record_fields_set_together(posting_suite):
    overdrawn = next(c for c in posting_suite["conditions"] if c["condition"] == "ACCT-BALANCE < 0")
    assert overdrawn["covered"] == [True, False]


def test_a_lowered_overdraft_fee_is_seen(posting_suite, tmp_path):
    assert replay(posting_suite, estate(tmp_path, "post-od-fee-down"), LocalRunner())


def test_the_wider_search_still_gives_the_same_suite_byte_for_byte(posting_suite, tmp_path):
    assert suite_of(estate(tmp_path), "POSTTXN") == posting_suite


def test_a_refactor_still_replays_clean(fee_suite, tmp_path):
    assert replay(fee_suite, estate(tmp_path, "fee-compute"), LocalRunner()) == []
