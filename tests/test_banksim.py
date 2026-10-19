"""Six synthetic banks and the change stream the engine scans for them (ADR 014)."""

import json
import subprocess

import pytest

from changeproof.adapters.cobol import CobolAdapter
from changeproof.banksim import BANKS, catalogue, render, tick
from changeproof.banksim.run import append, ledger, repository, restore, save, scorecard
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


def test_every_catalogued_change_applies_once_to_its_bank_estate(tmp_path):
    for bank in BANKS:
        root = tmp_path / bank.id
        render(bank, root)
        kinds = set()
        for change in catalogue(bank):
            text = (root / change.path).read_text()
            assert text.count(change.old) == 1, (bank.id, change.id)
            assert change.old != change.new
            assert max(map(len, text.replace(change.old, change.new).splitlines())) <= 72, (bank.id, change.id)
            kinds.add(change.kind)
        assert kinds == {"refactor", "defect", "intended"}


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
    row = {"day": 1, "bank": bank.id, "market": bank.market, "change": "intaccr-init", "outcome": "proven",
           "governance": {"outcome": "clean"}, "seconds": 9}
    append(first, [row])
    save(first, tmp_path / "keep")
    restore(tmp_path / "second", tmp_path / "keep")
    again = tmp_path / "second" / "banks" / bank.id
    assert git(again, "rev-parse", "main") == git(root, "rev-parse", "main")
    assert (again / "src" / "INTACCR.cbl").read_text() == (root / "src" / "INTACCR.cbl").read_text()
    assert ledger(tmp_path / "second") == [row]
    assert json.loads((tmp_path / "keep" / "scorecard.json").read_text())["by_outcome"] == {"proven": 1}
