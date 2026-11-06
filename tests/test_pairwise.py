"""Pairwise boundary search: the engine sets two inputs together around each boundary (sim MONTH-REPORT idea 1).

The bank estate's own programs are the fixtures. Each test names the simulation miss it reproduces.
"""

import pytest

from changeproof.banksim import BANKS, catalogue, render
from changeproof.characterize import LocalRunner, around, characterize, pairs, replay

BANK = BANKS[0]  # Prairie Ledger: retail minimum 1500.00, 200 free transactions, overdraft fee 35.00


# PURPOSE: THE BANK'S ESTATE WITH ONE CATALOGUED CHANGE APPLIED (OR NONE)
def estate(root, *change_ids):
    render(BANK, root)
    for change in catalogue(BANK):
        if change.id in change_ids:
            path = root / change.path
            path.write_text(path.read_text().replace(change.old, change.new, 1))
    return root


# PURPOSE: CHARACTERIZES ONE ESTATE PROGRAM, THEN REPLAYS THE SUITE AFTER A CATALOGUED CHANGE
def differences(tmp_path, program, change_id, *before_ids):
    root = estate(tmp_path, *before_ids)
    suite = characterize(root / "src" / f"{program}.cbl", root, LocalRunner())
    estate(tmp_path, change_id, *before_ids)
    return suite, replay(suite, root, LocalRunner())


def test_values_around_a_boundary_are_the_literal_and_one_unit_either_side_that_the_pool_holds():
    bounds = {"BAL": {"1500.00": {"b24"}}, "SEG": {"R": {"b23"}}, "N": {"200": {"b31"}}}
    pools = {"BAL": ["0.00", "1499.99", "1500.00", "1500.01"], "SEG": ["", "R"], "N": ["199", "200"]}
    assert around(bounds, pools) == {"BAL": {"1499.99": {"b24"}, "1500.00": {"b24"}, "1500.01": {"b24"}},
                                     "SEG": {"R": {"b23"}}, "N": {"199": {"b31"}, "200": {"b31"}}}


def test_pairs_set_two_fields_of_a_seed_together_over_every_pair_of_their_values():
    seed = {"A": "0", "B": "0", "C": "x"}
    found = pairs(seed, {"A": ["0", "1"], "B": ["0", "2"], "C": ["x", "y"]}, ["A", "B"])
    assert len(found) == 4 and {"A": "1", "B": "2", "C": "x"} in found
    assert all(f["C"] == "x" for f in found)


# sim miss post-od-fee-down x6: the fee line needs a debit above the balance but inside the limit
def test_a_debit_into_the_overdraft_limit_is_searched_and_the_fee_change_is_seen(tmp_path):
    suite, found = differences(tmp_path, "POSTTXN", "post-od-fee-down")
    fee = next(c for c in suite["conditions"] if c["condition"] == "ACCT-BALANCE < 0")
    assert fee["covered"] == [True, False]
    assert any(d["field"].endswith("ACCT-BALANCE") for d in found)


# sim miss fee-waiver-strict x6: the minimum was only ever tried with a business or student segment
def test_the_retail_waiver_runs_on_its_minimum_and_the_strict_test_is_seen(tmp_path):
    suite, found = differences(tmp_path, "FEEASSES", "fee-waiver-strict")
    minimum = BANK.rules["retail_minimum"]
    assert any(t["input"]["LK-SEGMENT"] == "R" and t["input"]["LK-AVG-BALANCE"] == minimum for t in suite["tests"])
    assert {d["field"] for d in found} >= {"LK-WAIVED", "LK-FEE"}


# sim miss fee-per-txn-slip x4: on an inclusive threshold the kept run multiplies the rate by zero
def test_a_run_one_past_an_inclusive_threshold_is_kept_and_the_rate_slip_is_seen(tmp_path):
    suite, found = differences(tmp_path, "FEEASSES", "fee-per-txn-slip", "fee-free-txns-inclusive")
    past = str(int(BANK.rules["free_txns"]) + 1)
    assert any(t["input"]["LK-SEGMENT"] == "B" and t["input"]["LK-TXN-COUNT"] == past for t in suite["tests"])
    assert any(d["field"] == "LK-FEE" for d in found)


@pytest.mark.parametrize("change_id", ["post-compute", "fee-compute", "fee-free-txns-inclusive"])
def test_refactors_still_replay_clean(tmp_path, change_id):
    program = "POSTTXN" if change_id.startswith("post") else "FEEASSES"
    assert differences(tmp_path, program, change_id)[1] == []
