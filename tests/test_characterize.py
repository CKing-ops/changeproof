"""Week 8: characterization tests. Boundary inputs run through GnuCOBOL; golden outputs linked to source."""

import json
from collections import Counter
from pathlib import Path

import pytest

from changeproof.adapters.cobol import CobolAdapter
from changeproof.characterize import (DockerRunner, LocalRunner, candidates, characterize, linkage_fields,
                                      outcomes, parse_picture, read_trace, replay)
from changeproof.cli import main

REPO = Path(__file__).resolve().parent.parent
CORPUS = REPO / "corpus" / "synthetic"
BATCH = ("FEECALC", "RISKSCR", "INTCALC")
GOLDEN = REPO / "docs" / "weekly" / "week08-golden"


def module(name, root=CORPUS):
    return CobolAdapter([]).parse(root / "batch" / f"{name}.cbl", root)


@pytest.fixture(scope="module")
def suites():
    return {name: characterize(CORPUS / "batch" / f"{name}.cbl", CORPUS, LocalRunner()) for name in BATCH}


def test_pictures_give_size_scale_and_sign():
    assert parse_picture("S9(7)V99") == {"numeric": True, "signed": True, "digits": 9, "scale": 2, "length": 9}
    assert parse_picture("9(3)") == {"numeric": True, "signed": False, "digits": 3, "scale": 0, "length": 3}
    assert parse_picture("X(8)") == {"numeric": False, "signed": False, "digits": 0, "scale": 0, "length": 8}


def test_linkage_fields_come_from_the_ir_with_their_88_values_and_lines():
    fields = {f.name: f for f in linkage_fields(module("FEECALC"))}
    assert list(fields) == ["LK-AMOUNT", "LK-CUST-TYPE", "LK-DAYS-LATE", "LK-FEE", "LK-REASON"]
    assert fields["LK-CUST-TYPE"].values == {"CUST-PERSONAL": "P", "CUST-BUSINESS": "B"}
    assert fields["LK-DAYS-LATE"].provenance.line == 10
    assert fields["LK-AMOUNT"].read and not fields["LK-REASON"].read


def test_linkage_items_the_driver_cannot_fill_are_refused(tmp_path):
    (tmp_path / "batch").mkdir()
    source = (CORPUS / "batch" / "FEECALC.cbl").read_text().replace("PIC S9(7)V99.", "PIC S9(7)V99 COMP-3.", 1)
    (tmp_path / "batch" / "FEECALC.cbl").write_text(source)
    with pytest.raises(ValueError, match="LK-AMOUNT.*COMP-3"):
        linkage_fields(module("FEECALC", tmp_path))


def test_boundary_candidates_sit_on_and_either_side_of_each_literal():
    fields = {f.name: f for f in linkage_fields(module("FEECALC"))}
    pool = candidates(fields["LK-DAYS-LATE"], module("FEECALC"))
    assert {"0", "29", "30", "31", "999"} <= set(pool)
    assert all(0 <= int(v) <= 999 for v in pool)
    assert {"P", "B", ""} <= set(candidates(fields["LK-CUST-TYPE"], module("FEECALC")))
    assert {"ST", "PR", "VP", ""} <= set(candidates({f.name: f for f in linkage_fields(module("INTCALC"))}
                                                    ["LK-RATE-CODE"], module("INTCALC")))
    assert candidates(fields["LK-REASON"], module("FEECALC")) == [""]


def test_traces_count_lines_of_the_program_under_test_only():
    trace = """Source: '/work/FEECALC.cbl'
Program-Id:  FEECALC              Entry: FEECALC                         Line:     13
Program-Id:  FEECALC                     IF                              Line:     18
Program-Id:  FEECALC                     IF                              Line:     18
Program-Id:  FEECALC                     ADD                             Line:     35
Source: '/work/drv.cbl'
Program-Id:  CPDRIVER                    CALL                            Line:     18
"""
    assert read_trace(trace, "FEECALC") == Counter({13: 1, 18: 2, 35: 1})


def test_outcomes_read_each_kind_of_branch_from_line_counts():
    branches = {b.provenance.line: b for b in module("RISKSCR").entities if b.kind == "branch"}
    assert outcomes(branches[25], Counter({25: 1, 26: 1})) == {True}
    assert outcomes(branches[25], Counter({25: 1, 28: 1})) == {False}
    assert outcomes(branches[35], Counter({35: 1})) == {False}
    assert outcomes(branches[32], Counter({32: 1})) == {True}
    assert outcomes(branches[32], Counter({32: 1, 33: 3})) == {True, False}
    assert outcomes(branches[41], Counter({38: 1, 42: 1})) == {True}
    assert outcomes(branches[41], Counter({38: 1, 40: 1})) == {False}
    assert outcomes(branches[41], Counter()) == set()


def test_a_run_through_the_adapter_returns_the_golden_output():
    found = CobolAdapter([], root=CORPUS).run(module("FEECALC"), {"LK-AMOUNT": "15000", "LK-CUST-TYPE": "P",
                                                                 "LK-DAYS-LATE": "45"})
    assert len(found) == 1
    assert found[0].entity_id == "program:FEECALC"
    assert found[0].outputs["LK-FEE"] == "+0000240.00"
    assert found[0].outputs["LK-REASON"] == "LATE    "
    assert (found[0].provenance.file, found[0].provenance.line) == ("batch/FEECALC.cbl", 1)


def test_exit_check_every_extracted_condition_has_a_test(suites):
    for name, suite in suites.items():
        assert suite["conditions"], name
        for condition in suite["conditions"]:
            assert condition["tests"], f"{name} {condition['id']} has no test"


def test_every_condition_is_seen_both_ways(suites):
    for name, suite in suites.items():
        for condition in suite["conditions"]:
            assert condition["covered"] == [True, False], f"{name} {condition['id']}"


def test_golden_outputs_link_to_the_source_lines_they_exercise(suites):
    for suite in suites.values():
        lines = (CORPUS / suite["source"]["file"]).read_text().splitlines()
        for condition in suite["conditions"]:
            where = condition["provenance"]
            assert condition["kind"].upper() in lines[where["line"] - 1].upper()
        ids = {c["id"] for c in suite["conditions"]}
        for test in suite["tests"]:
            assert test["covers"] and {c["condition"] for c in test["covers"]} <= ids
            assert test["rc"] == 0


def test_suites_are_reproducible(suites):
    again = characterize(CORPUS / "batch" / "RISKSCR.cbl", CORPUS, LocalRunner())
    assert json.dumps(again, sort_keys=True) == json.dumps(suites["RISKSCR"], sort_keys=True)
    assert replay(suites["INTCALC"], CORPUS, LocalRunner()) == []


def test_replay_catches_a_changed_behaviour(suites, tmp_path):
    (tmp_path / "batch").mkdir()
    source = (CORPUS / "batch" / "FEECALC.cbl").read_text().replace("LK-AMOUNT * 0.015", "LK-AMOUNT * 0.016")
    (tmp_path / "batch" / "FEECALC.cbl").write_text(source)
    broken = replay(suites["FEECALC"], tmp_path, LocalRunner())
    assert broken and all(b["field"] == "LK-FEE" for b in broken)


def test_replay_refuses_a_suite_for_another_program(suites):
    with pytest.raises(ValueError, match="FEECALC"):
        replay(suites["FEECALC"] | {"source": suites["INTCALC"]["source"]}, CORPUS, LocalRunner())


def test_committed_golden_suites_still_hold():
    for name in BATCH:
        suite = json.loads((GOLDEN / f"{name}.json").read_text())
        assert suite["source"]["file"] == f"corpus/synthetic/batch/{name}.cbl"
        assert replay(suite, REPO, LocalRunner()) == []


def test_the_docker_runner_has_no_network_and_sees_only_its_work_folder(tmp_path):
    argv = DockerRunner("changeproof-gnucobol").command(tmp_path)
    assert argv[:3] == ["docker", "run", "--rm"]
    assert argv[argv.index("--network") + 1] == "none"
    assert f"{tmp_path}:/work" in argv
    assert argv[-3:] == ["sh", "/work/run.sh", "/work"]


def test_cli_characterize_writes_a_suite_per_program(tmp_path, capsys):
    assert main(["characterize", str(CORPUS / "batch" / "INTCALC.cbl"), "--root", str(CORPUS),
                 "--out", str(tmp_path)]) == 0
    suite = json.loads((tmp_path / "INTCALC.json").read_text())
    assert suite["program"] == "INTCALC"
    summary = json.loads(capsys.readouterr().out)
    assert summary["INTCALC"]["conditions"] == 7
    assert summary["INTCALC"]["untested"] == []
    assert main(["characterize", "--replay", str(tmp_path / "INTCALC.json"), "--root", str(CORPUS)]) == 0


def test_the_container_and_ci_pin_the_same_gnucobol():
    pin = "gnucobol3=3.1.2-5.1ubuntu1"
    assert pin in (REPO / "docker" / "gnucobol" / "Dockerfile").read_text()
    assert pin in (REPO / ".github" / "workflows" / "ci.yml").read_text()
