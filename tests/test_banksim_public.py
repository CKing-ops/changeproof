"""A simulated bank that also runs IBM's public Cash Account service (ADR 017)."""

import subprocess

import pytest

from changeproof.banksim.public import CORPUS, HOST, LAYOUT, catalogue, graft, scan
from changeproof.characterize import LocalRunner
from changeproof.config import load_config
from changeproof.impact import impact


def test_the_corpus_is_the_pinned_upstream_under_apache_2():
    source = (CORPUS / "SOURCE.md").read_text()
    assert "https://github.com/IBMStockTrader/cash-account-cobol" in source
    assert "c35db0d1f283367109bcd5dfadd76560cf53b2dc" in source
    assert (CORPUS / "LICENSE").read_text().split()[:4] == ["Apache", "License", "Version", "2.0,"]


def test_the_host_bank_runs_the_cash_account_unmodified_beside_its_own_programs(tmp_path):
    graft(HOST, tmp_path)
    for upstream, here in LAYOUT.items():
        assert (tmp_path / here).read_bytes() == (CORPUS / upstream).read_bytes(), here
    assert {p.name for p in (tmp_path / "src").glob("*.cbl")} >= {"INTACCR.cbl", "POSTTXN.cbl"}
    config = load_config(tmp_path / "changeproof.yaml")
    cash = next(c for c in config.components if c.id == "cash-account")
    assert (cash.path, cash.criticality.value, config.market) == ("cash", "high", HOST.market)


def test_every_cash_account_change_applies_once_and_says_what_it_must_reach(tmp_path):
    graft(HOST, tmp_path)
    changes = catalogue()
    assert {c.kind for c in changes} == {"refactor", "defect", "intended"}
    assert len({c.id for c in changes}) == len(changes)
    for change in changes:
        assert (tmp_path / change.path).read_text(encoding="latin-1").count(change.old) == 1, change.id
        assert change.path.startswith("cash/")


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
                          check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture(scope="module")
def estate(tmp_path_factory):
    root = tmp_path_factory.mktemp("cash") / "bank"
    graft(HOST, root)
    git(root, "init", "-q", "-b", "main")
    git(root, "add", "-A")
    git(root, "commit", "-qm", "import")
    return root


@pytest.mark.parametrize("change", catalogue(), ids=lambda c: c.id)
def test_impact_reaches_what_each_cash_account_change_really_touches(estate, change):
    path = estate / change.path
    text = path.read_text(encoding="latin-1")
    path.write_text(text.replace(change.old, change.new, 1), encoding="latin-1")
    git(estate, "commit", "-qam", change.summary)
    try:
        found = impact(estate, "HEAD", copybook_dirs=["cash/copy"])
    finally:
        git(estate, "reset", "-q", "--hard", "HEAD~1")
    seen = {c["id"] for c in found["changed"]} | {i["id"] for i in found["impacted"]}
    assert change.reaches <= seen, sorted(change.reaches - seen)
    assert all(i["provenance"]["file"] and i["provenance"]["line"] for i in found["impacted"])


@pytest.fixture(scope="module")
def days(tmp_path_factory):
    state = tmp_path_factory.mktemp("public")
    return [scan(state, n, LocalRunner(), only=only)
            for n, only in enumerate(("cash-credit-sign", "cash-ddl-widen"), 1)]


def test_a_cics_defect_is_reported_inconclusive_never_proven(days):
    row = days[0]
    assert (row["change"], row["truth"]["behaviour"]) == ("cash-credit-sign", "different")
    assert row["engine"]["verdict"] == "inconclusive" and row["outcome"] == "inconclusive"
    assert row["engine"]["untested"] == [
        "CASH00: no baseline: uses EXEC SQL at cash/copy/DCLCASH.cpy:8-12; stand-ins for CICS, Db2 and IMS calls are planned"]
    assert row["engine"]["tests"] > 0 and row["engine"]["different"] == 0
    assert row["impact"]["outcome"] == "reached" and row["provenance"] == {"file": "cash/src/CASH00.cbl", "line": 222}


def test_a_ddl_change_reaches_the_program_through_its_table(days):
    row = days[1]
    assert row["impact"] == {"expected": ["program:CASH00", "table:STOCKTRD.CASHACCOUNTY"],
                             "missing": [], "outcome": "reached"}
    assert row["provenance"]["file"] == "cash/jcl/DB2DDL.jcl"


def test_approvals_are_scored_from_the_change_record_and_main_stays_clean(days):
    for row in days:
        assert row["governance"]["expected_flag"] == (row["truth"]["governance"] != "governed")
        assert row["governance"]["outcome"] in ("flagged", "clean", "missed", "false-flag")
        assert not row["merged"]
