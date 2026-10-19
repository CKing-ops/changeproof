"""COBOL behaviour check beyond display linkage items: packed and binary numbers, tables, redefinitions,
and batch jobs that read and write files. CICS and Db2 programs are refused with their statement's line."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from changeproof.adapters.cobol import CobolAdapter
from changeproof.adapters.cobol.gnucobol import FIXED_CLOCK
from changeproof.characterize import LocalRunner, characterize, input_fields, replay
from changeproof.equivalence import equivalence

HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures" / "cobol_io"
CARDDEMO = HERE.parent / "corpus" / "carddemo"


def module(name, root=FIXTURES):
    return CobolAdapter([]).parse(root / f"{name}.cbl", root)


def planted(tmp_path, name, old, new):
    text = (FIXTURES / f"{name}.cbl").read_text()
    assert old in text
    (tmp_path / f"{name}.cbl").write_text(text.replace(old, new, 1))
    return tmp_path


@pytest.fixture(scope="module")
def suites():
    return {name: characterize(FIXTURES / f"{name}.cbl", FIXTURES, LocalRunner()) for name in ("PAYCALC", "POSTBAL")}


def test_packed_binary_table_and_redefined_items_become_inputs_with_their_usage():
    fields = {f.key: f for f in input_fields(module("PAYCALC"))}
    assert list(fields) == ["LK-GROSS", "LK-HOURS", "LK-RATE(1)", "LK-RATE(2)", "LK-RATE(3)", "LK-BAND",
                            "LK-YEAR", "LK-MONTH", "LK-DAY", "LK-NET", "LK-FLAG"]
    assert (fields["LK-GROSS"].usage, fields["LK-HOURS"].usage) == ("COMP-3", "COMP")
    assert fields["LK-RATE(2)"].provenance.line == 10
    # the date is filled through the view the program reads, not the redefined text
    assert "LK-DATE" not in fields and fields["LK-MONTH"].read


def test_items_the_driver_cannot_fill_are_still_refused_with_their_line(tmp_path):
    root = planted(tmp_path, "PAYCALC", "PIC S9(4) COMP.", "USAGE POINTER.")
    with pytest.raises(ValueError, match=r"LK-HOURS at PAYCALC.cbl:8.*POINTER"):
        input_fields(module("PAYCALC", root))


def test_a_packed_decimal_subprogram_is_characterized_down_every_branch(suites):
    suite = suites["PAYCALC"]
    assert all(c["covered"] == [True, False] for c in suite["conditions"]), suite["conditions"]
    flags = {t["output"]["LK-FLAG"] for t in suite["tests"]}
    assert {"B", "N", "O", "X"} <= flags
    month_end = next(t for t in suite["tests"] if t["output"]["LK-FLAG"] == "X")
    assert month_end["input"]["LK-MONTH"] == "12"
    assert month_end["output"]["LK-DATE"][4:6] == "12"


def test_replay_of_a_packed_decimal_subprogram_catches_a_changed_overtime_bonus(suites, tmp_path):
    assert replay(suites["PAYCALC"], FIXTURES, LocalRunner()) == []
    root = planted(tmp_path, "PAYCALC", "ADD 50 TO LK-NET", "ADD 55 TO LK-NET")
    assert {d["field"] for d in replay(suites["PAYCALC"], root, LocalRunner())} == {"LK-NET"}


def test_a_batch_job_runs_on_generated_files_and_its_output_files_are_read_back(suites):
    suite = suites["POSTBAL"]
    assert all(c["covered"] == [True, False] for c in suite["conditions"]), suite["conditions"]
    reasons = {t["output"].get("REJECT-FILE#00001.REJ-REASON", "").strip() for t in suite["tests"]}
    assert {"NOACCOUNT", "OVERLIMIT", "BADTYPE"} <= reasons
    rejected = next(t for t in suite["tests"] if "REJECT-FILE#00001.REJ-DATE" in t["output"])
    assert rejected["output"]["REJECT-FILE#00001.REJ-DATE"] == FIXED_CLOCK[:10].replace("/", "")
    assert rejected["rc"] == 4 and "REJECTED 00001" in rejected["output"]["SYSOUT"]
    posted = [t for t in suite["tests"] if "POSTED 00001" in t["output"]["SYSOUT"]]
    assert posted and all("ACCT-FILE#00001.ACCT-BALANCE" in t["output"] for t in posted)
    assert any(t["input"]["TRAN-FILE:records"] == "0" for t in suite["tests"])


def test_the_same_batch_suite_comes_out_byte_for_byte(suites):
    again = characterize(FIXTURES / "POSTBAL.cbl", FIXTURES, LocalRunner())
    assert json.dumps(again, sort_keys=True) == json.dumps(suites["POSTBAL"], sort_keys=True)


def test_replay_of_a_batch_job_catches_a_changed_posting_rule(suites, tmp_path):
    assert replay(suites["POSTBAL"], FIXTURES, LocalRunner()) == []
    root = planted(tmp_path, "POSTBAL", "ADD TRAN-AMOUNT TO ACCT-BALANCE", "SUBTRACT TRAN-AMOUNT FROM ACCT-BALANCE")
    assert "ACCT-FILE#00001.ACCT-BALANCE" in {d["field"] for d in replay(suites["POSTBAL"], root, LocalRunner())}


def test_cics_programs_are_refused_with_the_line_of_their_first_exec_block():
    adapter = CobolAdapter(["app/cpy"])
    found = adapter.parse(CARDDEMO / "app" / "cbl" / "COACTVWC.cbl", CARDDEMO)
    with pytest.raises(ValueError, match=r"EXEC CICS at app/cbl/COACTVWC.cbl:\d+.*planned"):
        input_fields(found)


def git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True,
                   env={"GIT_AUTHOR_NAME": "Priya Raman", "GIT_AUTHOR_EMAIL": "priya@billing.example",
                        "GIT_COMMITTER_NAME": "Priya Raman", "GIT_COMMITTER_EMAIL": "priya@billing.example",
                        "GIT_AUTHOR_DATE": "2026-10-01T09:00:00Z", "GIT_COMMITTER_DATE": "2026-10-01T09:00:00Z",
                        "PATH": "/usr/bin:/bin"})


def test_equivalence_now_tests_batch_jobs_and_packed_subprograms_outside_the_impact_set(tmp_path):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    for name in ("PAYCALC", "POSTBAL"):
        shutil.copy(FIXTURES / f"{name}.cbl", root / "src")
    shutil.copy(HERE.parent / "corpus" / "synthetic" / "batch" / "FEECALC.cbl", root / "src")
    git(root, "init", "-q", "-b", "main")
    git(root, "add", ".")
    git(root, "commit", "-q", "-m", "BILL-1: Import")
    fee = root / "src" / "FEECALC.cbl"
    fee.write_text(fee.read_text().replace("ADD 40 TO LK-FEE", "COMPUTE LK-FEE = LK-FEE + 40"))
    git(root, "commit", "-q", "-am", "BILL-2: Write the late fee as a COMPUTE")
    p = equivalence(root, "HEAD", runner=LocalRunner()).predicate
    assert p["untested"] == []
    assert {t["target"]["name"] for t in p["tests"]} == {"PAYCALC", "POSTBAL"}
    assert p["verdict"] == "equivalent"


def test_carddemo_posting_job_is_characterized_and_a_reversed_balance_update_is_caught(tmp_path):
    suite = characterize(CARDDEMO / "app" / "cbl" / "CBTRN02C.cbl", CARDDEMO, LocalRunner(), ["app/cpy"])
    assert len(suite["tests"]) > 1 and {0, 4} <= {t["rc"] for t in suite["tests"]}
    assert replay(suite, CARDDEMO, LocalRunner(), ["app/cpy"]) == []
    shutil.copytree(CARDDEMO / "app" / "cpy", tmp_path / "app" / "cpy")
    (tmp_path / "app" / "cbl").mkdir()
    text = (CARDDEMO / "app" / "cbl" / "CBTRN02C.cbl").read_text()
    (tmp_path / "app" / "cbl" / "CBTRN02C.cbl").write_text(
        text.replace("ADD DALYTRAN-AMT  TO ACCT-CURR-BAL", "SUBTRACT DALYTRAN-AMT FROM ACCT-CURR-BAL", 1))
    assert any("ACCT-CURR-BAL" in d["field"] for d in replay(suite, tmp_path, LocalRunner(), ["app/cpy"]))
