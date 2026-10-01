"""Week 8: decisions in COBOL become `branch` entities: IF, each EVALUATE WHEN and PERFORM UNTIL."""

from pathlib import Path

import pytest

from changeproof.adapters.cobol import CobolAdapter

CORPUS = Path(__file__).resolve().parent.parent / "corpus" / "synthetic"


@pytest.fixture(scope="module")
def branches():
    found = {}
    for name in ("FEECALC", "RISKSCR", "INTCALC"):
        module = CobolAdapter([]).parse(CORPUS / "batch" / f"{name}.cbl", CORPUS)
        found[name] = [e for e in module.entities if e.kind == "branch"]
    return found


def test_every_decision_is_a_branch_on_its_line(branches):
    assert [(b.attributes["kind"], b.provenance.line) for b in branches["FEECALC"]] == [
        ("if", 18), ("when", 23), ("when", 25), ("if", 31), ("if", 34), ("if", 38)]
    assert [(b.attributes["kind"], b.provenance.line) for b in branches["RISKSCR"]] == [
        ("if", 20), ("if", 25), ("if", 28), ("until", 32), ("if", 35), ("when", 39), ("when", 41), ("when", 43)]
    assert [(b.attributes["kind"], b.provenance.line) for b in branches["INTCALC"]] == [
        ("when", 20), ("when", 22), ("when", 24), ("if", 30), ("if", 34), ("if", 41), ("if", 44)]


def test_branches_record_their_condition_and_the_lines_each_outcome_runs(branches):
    late = branches["FEECALC"][4]
    assert late.id == "branch:FEECALC.MAIN-PARA#5"
    assert (late.attributes["condition"], late.attributes["refs"]) == ("LK-DAYS-LATE > 30", ["LK-DAYS-LATE"])
    assert (late.attributes["true_line"], late.attributes["false_line"]) == (35, None)
    util = branches["RISKSCR"][1]
    assert (util.attributes["true_line"], util.attributes["false_line"]) == (26, 28)
    loop = branches["RISKSCR"][3]
    assert (loop.attributes["condition"], loop.attributes["true_line"], loop.attributes["false_line"]) == \
        ("WS-I > LK-MISSED", None, 33)


def test_evaluate_subjects_join_each_when(branches):
    standard = branches["INTCALC"][0]
    assert standard.attributes["condition"] == "LK-RATE-CODE = 'ST'"
    assert (standard.attributes["true_line"], standard.attributes["decision_line"]) == (21, 19)
    personal = branches["FEECALC"][1]
    assert (personal.attributes["condition"], personal.attributes["refs"]) == ("CUST-PERSONAL", ["CUST-PERSONAL"])


def test_the_program_records_its_using_parameters_in_call_order():
    module = CobolAdapter([]).parse(CORPUS / "batch" / "RISKSCR.cbl", CORPUS)
    assert module.entities[0].attributes["using"] == ["LK-BALANCE", "LK-LIMIT", "LK-MISSED", "LK-YEARS",
                                                      "LK-SCORE", "LK-GRADE"]
