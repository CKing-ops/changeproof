"""Six synthetic banks and the change stream the engine scans for them (ADR 014)."""

import json
import random
import subprocess
from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from changeproof.adapters.cobol import CobolAdapter
from changeproof.banksim import BANKS, catalogue, render, tick
from changeproof.banksim.audit import witness
from changeproof.banksim.estate import PROGRAMS, current
from changeproof.banksim.operations import (
    ACCOUNTS,
    open_accounts,
    run_rows,
    settle,
    traffic,
)
from changeproof.banksim.record import page
from changeproof.banksim.run import (
    FIRST_DAY,
    OPERATIONS,
    append,
    draw,
    ledger,
    repository,
    restore,
    save,
    scorecard,
)
from changeproof.characterize import LocalRunner
from changeproof.config import load_config


def test_three_us_banks_on_the_general_profile_and_three_eu_banks_on_dora():
    markets = {}
    for bank in BANKS:
        markets.setdefault(bank.market, []).append(bank.region)
    assert markets == {"general": ["us"] * 3, "eu-dora": ["eu"] * 3}
    assert len({b.id for b in BANKS}) == len({b.name for b in BANKS}) == 6
    assert {b.currency for b in BANKS if b.region == "eu"} == {"EUR"}


def test_every_bank_estate_parses_and_its_config_loads(tmp_path):
    adapter = CobolAdapter([])
    for bank in BANKS:
        root = tmp_path / bank.id
        render(bank, root)
        assert load_config(root / "changeproof.yaml").market == bank.market
        for path in sorted((root / "src").glob("*.cbl")):
            text = path.read_text()
            assert "{" not in text and max(map(len, text.splitlines())) <= 72, path
            assert bank.name in text
            names = [e.name for e in adapter.parse(path, root).entities if e.kind == "program"]
            assert names == [path.stem]


def test_every_catalogued_change_applies_to_its_bank_estate(tmp_path):
    for bank in BANKS:
        root = tmp_path / bank.id
        render(bank, root)
        kinds = set()
        changes = {c.id: c for c in catalogue(bank)}
        for change in changes.values():
            text = (root / change.path).read_text()
            if change.id.endswith("-back"):
                text = text.replace(change.new, change.old)
            assert text.count(change.old) == change.count, (bank.id, change.id)
            assert change.old != change.new
            assert max(map(len, text.replace(change.old, change.new).splitlines())) <= 72, (bank.id, change.id)
            kinds.add(change.kind)
        assert kinds == {"refactor", "defect", "intended"}
        assert {f"{c.id}-back" for c in changes.values() if c.kind == "refactor" and not c.id.endswith("-back")} \
            <= changes.keys()
        assert {Path(c.path).stem for c in changes.values()} == set(PROGRAMS)


def test_the_rules_are_read_back_from_the_tree_after_an_intended_change(tmp_path):
    for bank in (BANKS[0], BANKS[3]):
        root = tmp_path / bank.id
        render(bank, root)
        assert current(bank, root) == bank.rules
        for change in (c for c in catalogue(bank) if c.kind == "intended"):
            path = root / change.path
            before = path.read_text()
            path.write_text(before.replace(change.old, change.new))
            moved = {k for k, v in current(bank, root).items() if v != bank.rules[k]}
            assert len(moved) == 1, (bank.id, change.id, moved)
            assert any(c.id == change.id.replace("-up", "-down").replace("-down", "-up") or c.id == change.id
                       for c in catalogue(bank, current(bank, root)))
            path.write_text(before)


def test_the_draw_mixes_kinds_and_favours_changes_a_bank_has_seen_least():
    bank = BANKS[1]
    changes = catalogue(bank)
    seen = Counter({c.id: 200 for c in changes if c.id == "intaccr-basis"})
    rng = random.Random(7)
    drawn = Counter(draw(rng, changes, seen) for _ in range(3000))
    kinds = Counter(c.kind for c in drawn.elements())
    assert kinds["defect"] > kinds["intended"] > kinds["refactor"] > 300
    basis = next(c for c in changes if c.id == "intaccr-basis")
    assert drawn[basis] < 10 < min(n for c, n in drawn.items() if c.kind == "defect" and c is not basis)


def test_a_bank_started_before_a_program_existed_onboards_it_in_one_commit(tmp_path):
    bank = BANKS[2]
    root = repository(bank, tmp_path)
    for name in ("LOANPMT", "FXCONV", "CASHAGG"):
        (root / "src" / f"{name}.cbl").unlink()
    git(root, "commit", "-q", "-am", "drop", "--author", "x <x@example.invalid>")
    again = repository(bank, tmp_path, 9)
    assert sorted(p.stem for p in (again / "src").glob("*.cbl")) == sorted(PROGRAMS)
    assert git(again, "log", "-1", "--format=%s").strip() == "TRUST-2: Onboard LOANPMT, FXCONV, CASHAGG"
    assert git(again, "status", "--porcelain") == ""


def test_every_new_program_change_does_what_its_label_says_when_run(tmp_path):
    bank = BANKS[3]
    runner = LocalRunner()
    found = [witness(bank, c, runner) for c in catalogue(bank)
             if Path(c.path).stem in ("LOANPMT", "FXCONV", "CASHAGG")]
    assert [w["change"] for w in found if not w["agrees"]] == []
    assert {w["kind"] for w in found} == {"refactor", "defect", "intended"}


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture(scope="module")
def day(tmp_path_factory):
    state = tmp_path_factory.mktemp("sim")
    bank = next(b for b in BANKS if b.region == "eu")
    rows = [tick(bank, state, n, LocalRunner(), only=only) for n, only in
            enumerate(("intaccr-truncate", "intaccr-init", "paysc-report-strict"), 1)]
    return bank, state, rows


def test_a_planted_defect_is_caught_and_kept_off_main(day):
    bank, state, rows = day
    row = rows[0]
    assert (row["change"], row["truth"]["behaviour"], row["engine"]["verdict"]) == \
        ("intaccr-truncate", "different", "not-equivalent")
    assert row["outcome"] == "caught" and not row["merged"]
    assert "ROUNDED" in (state / "banks" / bank.id / "src" / "INTACCR.cbl").read_text()
    assert row["engine"]["different"] > 0 and row["provenance"]["file"] == "src/INTACCR.cbl"


def test_a_refactor_is_proven_equivalent_and_merged(day):
    _, _, rows = day
    row = rows[1]
    assert (row["truth"]["behaviour"], row["engine"]["verdict"], row["outcome"]) == ("same", "equivalent", "proven")
    assert row["merged"] and row["engine"]["different"] == 0


def test_governance_is_scored_from_the_change_record(day):
    _, _, rows = day
    for row in rows:
        assert row["governance"]["expected_flag"] == (row["truth"]["governance"] != "governed")
        assert row["governance"]["outcome"] in ("flagged", "clean", "missed", "false-flag")
        if row["governance"]["outcome"] in ("flagged", "false-flag"):
            assert row["governance"]["open_items"]


def test_the_ledger_and_scorecard_add_up_and_the_stream_repeats(day, tmp_path):
    bank, state, rows = day
    ledger = [json.loads(line) for line in (state / "ledger.jsonl").read_text().splitlines()]
    assert ledger == rows
    card = scorecard(ledger)
    assert card["changes"] == 3 and card["by_outcome"] == {"caught": 2, "proven": 1}
    assert card["by_market"]["eu-dora"]["changes"] == 3
    again = tick(bank, tmp_path, 1, LocalRunner(), only="intaccr-truncate")
    assert {k: again[k] for k in ("change", "truth", "outcome")} == {k: rows[0][k] for k in ("change", "truth", "outcome")}
    assert git(tmp_path / "banks" / bank.id, "rev-parse", "main") == \
        git(state / "banks" / bank.id, "rev-list", "--max-parents=0", "main")


def test_a_saved_simulation_carries_on_from_its_bundles_on_a_fresh_machine(tmp_path):
    bank = BANKS[0]
    first = tmp_path / "first"
    root = repository(bank, first)
    row = {"day": 1, "date": "2026-10-21", "bank": bank.id, "market": bank.market, "change": "intaccr-init",
           "kind": "refactor", "outcome": "proven", "provenance": {"file": "src/INTACCR.cbl", "line": 20},
           "governance": {"outcome": "clean"}, "seconds": 9}
    append(first, [row])
    save(first, tmp_path / "keep")
    restore(tmp_path / "second", tmp_path / "keep")
    again = tmp_path / "second" / "banks" / bank.id
    assert git(again, "rev-parse", "main") == git(root, "rev-parse", "main")
    assert (again / "src" / "INTACCR.cbl").read_text() == (root / "src" / "INTACCR.cbl").read_text()
    assert ledger(tmp_path / "second") == [row]
    assert json.loads((tmp_path / "keep" / "scorecard.json").read_text())["by_outcome"] == {"proven": 1}
    assert "| Refactors proven equivalent | 1 of 1 (100%) | 1 of 1 (100%) | - |" in (tmp_path / "keep" / "RECORD.md").read_text()


def test_each_bank_opens_the_same_book_of_invented_accounts():
    for bank in BANKS:
        book = open_accounts(bank)
        assert book == open_accounts(bank) and len(book) == ACCOUNTS == len({a.id for a in book})
        assert {a.product for a in book} == {"S", "C"} and {a.segment for a in book} == {"R", "B", "S"}
        assert all(a.limit == "0" for a in book if a.product == "S")
    assert open_accounts(BANKS[0]) != open_accounts(BANKS[1])


def test_a_days_traffic_accrues_interest_on_every_account_and_charges_fees_only_at_month_end():
    bank = BANKS[3]
    book = open_accounts(bank)
    weekday = traffic(bank, book, 3, date(2026, 10, 23))
    assert len(weekday["INTACCR"]) == ACCOUNTS and weekday["FEEASSES"] == []
    assert 40 <= len(weekday["POSTTXN"]) <= 80 and 25 <= len(weekday["PAYSCRN"]) <= 50
    assert 12 <= len(weekday["LOANPMT"]) <= 30 and 8 <= len(weekday["FXCONV"]) <= 20
    assert 20 <= len(weekday["CASHAGG"])
    assert {r["LK-CURRENCY"] for r in weekday["PAYSCRN"]} <= {"EUR", "USD", "GBP", "CHF"}
    assert len(traffic(bank, book, 11, date(2026, 10, 31))["FEEASSES"]) == ACCOUNTS
    assert weekday == traffic(bank, book, 3, date(2026, 10, 23))


def test_the_banks_run_their_business_on_main_and_live_traffic_shows_a_caught_defect(day):
    bank, state, rows = day
    assert rows[0]["traffic"] == {"program": "INTACCR", "runs": ACCOUNTS, "different": rows[0]["traffic"]["different"]}
    assert rows[0]["traffic"]["different"] > 0
    days = ledger(state, OPERATIONS)
    assert [o["day"] for o in days] == [1, 2, 3] and days[0]["date"] == str(FIRST_DAY + timedelta(days=1))
    opening = sum(Decimal(a.balance) for a in open_accounts(bank))
    assert Decimal(days[0]["deposits"]) != opening and Decimal(days[0]["interest"]) > 0
    assert days[0]["posted"] + days[0]["rejected"] == days[0]["postings"]


def test_the_one_page_record_counts_only_what_the_ledgers_hold(day):
    _, state, rows = day
    text = page(rows, ledger(state, OPERATIONS))
    assert "| Defects caught | 2 of 2 (100%) | - | 2 of 2 (100%) |" in text
    assert "| Refactors proven equivalent | 1 of 1 (100%) | - | 1 of 1 (100%) |" in text
    assert "## Each bank's business on 2026-10-23" in text and "aldercove" in text
    assert "| 2026-10 | 3 |" in text


def test_cash_rows_carry_the_customers_earlier_cash_that_day_and_some_sit_on_the_threshold():
    bank = BANKS[0]
    book = open_accounts(bank)
    rows = [r for n in range(1, 30) for r in traffic(bank, book, n, FIRST_DAY + timedelta(days=n))["CASHAGG"]]
    assert any(Decimal(r["LK-CASH-TODAY"]) > 0 for r in rows)
    assert any(r["LK-AMOUNT"] == bank.rules["cash_threshold"] for r in rows)
    assert all(r["LK-KIND"] in "IOQ" for r in rows)


def test_a_days_new_business_is_settled_from_the_programs_outputs(tmp_path):
    bank = BANKS[4]
    render(bank, tmp_path)
    book = open_accounts(bank)
    on = date(2026, 10, 23)
    today = traffic(bank, book, 3, on)
    results = {p: run_rows(tmp_path, p, today[p], LocalRunner()) for p in PROGRAMS}
    day = settle(book, today, results, on)
    assert day["loans"]["installments"] == len(today["LOANPMT"]) and Decimal(day["loans"]["interest"]) > 0
    assert sum(day["fx"]["decisions"].values()) == len(today["FXCONV"])
    assert day["cash"]["transactions"] == len(today["CASHAGG"]) and day["cash"]["reported"] > 0
