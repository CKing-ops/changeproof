"""Week 10 problem 1: pick the fewest characterization tests that still cover what a change touches."""

import importlib.util
import json
from pathlib import Path

import pytest

from changeproof.characterize import LocalRunner, characterize, replay
from changeproof.cli import main
from changeproof.selection import changed_lines, obligations, select_tests, selection_problem, subset
from changeproof.solver import brute_force, cover_qubo, solve

HERE = Path(__file__).resolve().parent
CORPUS = HERE.parent / "corpus" / "synthetic"
BATCH = ("FEECALC", "RISKSCR", "INTCALC")

_spec = importlib.util.spec_from_file_location("selection_bugs", HERE / "fixtures" / "equivalence" / "bugs.py")
bugs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bugs)


@pytest.fixture(scope="module")
def suites():
    return {name: characterize(CORPUS / "batch" / f"{name}.cbl", CORPUS, LocalRunner()) for name in BATCH}


def source(name):
    return (CORPUS / "batch" / f"{name}.cbl").read_text()


def test_each_test_records_the_lines_it_ran_and_its_boundary_points(suites):
    for suite in suites.values():
        decision = {c["id"]: c["decision_line"] for c in suite["conditions"]}
        for test in suite["tests"]:
            assert test["lines"] == sorted(set(test["lines"]))
            assert {decision[c["condition"]] for c in test["covers"]} <= set(test["lines"])
            for point in test["boundaries"]:
                assert test["input"][point["field"]] == point["value"]
                assert point["condition"] in {c["condition"] for c in test["covers"]}
    # FEECALC's late-fee test sits on DAYS-LATE = 30, the literal its IF compares with
    feecalc = suites["FEECALC"]["tests"]
    assert any(p["field"] == "LK-DAYS-LATE" and p["value"] == "30" for t in feecalc for p in t["boundaries"])


def test_changed_lines_are_numbered_in_the_base_source():
    assert changed_lines("a\nb\nc\n", "a\nB\nc\n") == {2}
    assert changed_lines("a\nb\nc\n", "a\nc\n") == {2}
    assert changed_lines("a\nb\nc\n", "a\nx\nb\nc\n") == {1, 2}  # an insertion touches the lines either side
    assert changed_lines("a\n", "a\n") == set()


def test_a_changed_condition_needs_both_outcomes_and_its_boundary_points(suites):
    suite = suites["FEECALC"]
    late = next(c for c in suite["conditions"] if c["condition"] == "LK-DAYS-LATE > 30")
    needed = set().union(*obligations(suite, {late["provenance"]["line"]}).values())
    assert {f"{late['id']}=True", f"{late['id']}=False", f"{late['id']}@LK-DAYS-LATE=30"} <= needed


def test_a_change_no_test_runs_needs_no_test(suites):
    found = select_tests(suites["FEECALC"], {3})  # a comment line
    assert found.selection == () and found.objective == 0


def test_cp_sat_picks_no_more_tests_than_greedy_and_fewer_than_the_full_suite(suites):
    full = picked = 0
    for bug in bugs.BUGS:
        suite = suites[bug.program]
        lines = changed_lines(source(bug.program), bugs.apply(source(bug.program), bug))
        best, greedy = select_tests(suite, lines), select_tests(suite, lines, method="greedy")
        assert best.optimal and best.objective <= greedy.objective
        full += len(suite["tests"])
        picked += len(best.selection)
    assert picked < 0.65 * full  # 206 of 342 when written: every path through each change is kept


def caught(suite, root):
    return bool(replay(suite, root, LocalRunner()))


def mutant(tmp_path, bug):
    (tmp_path / "batch").mkdir(parents=True)
    (tmp_path / "batch" / f"{bug.program}.cbl").write_text(bugs.apply(source(bug.program), bug))
    return tmp_path


def test_exit_check_selected_subsets_catch_the_same_mutations_as_the_full_suite(suites, tmp_path):
    for bug in bugs.BUGS + bugs.HELD_OUT:
        suite = suites[bug.program]
        lines = changed_lines(source(bug.program), bugs.apply(source(bug.program), bug))
        root = mutant(tmp_path / bug.id, bug)
        full = caught(suite, root)
        for method in ("cp-sat", "greedy"):
            chosen = subset(suite, select_tests(suite, lines, method=method).selection)
            assert caught(chosen, root) == full, (bug.id, method)


def test_the_selection_qubo_has_the_classical_minimum_where_brute_force_reaches(suites):
    checked = 0
    for bug in bugs.BUGS:
        suite = suites[bug.program]
        problem = selection_problem(suite, changed_lines(source(bug.program), bugs.apply(source(bug.program), bug)))
        qubo, decode = cover_qubo(problem)
        if len(qubo.variables) > 20:
            continue
        energy, bits = brute_force(qubo)
        assert energy == solve(problem).objective == len(decode(bits))
        checked += 1
    assert checked >= 5


def test_cli_select_prints_the_subset_and_can_export_the_qubo(suites, tmp_path, capsys):
    suite_path = tmp_path / "FEECALC.json"
    suite_path.write_text(json.dumps(suites["FEECALC"]))
    head = tmp_path / "head.cbl"
    head.write_text(source("FEECALC").replace("IF LK-DAYS-LATE > 30", "IF LK-DAYS-LATE > 31"))
    qubo = tmp_path / "selection.qubo.json"
    assert main(["select", str(suite_path), "--head", str(head), "--root", str(CORPUS), "--qubo", str(qubo)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["program"] == "FEECALC" and out["method"] == "cp-sat" and out["optimal"]
    assert out["changed_lines"] == [34]
    assert 0 < len(out["tests"]) < len(suites["FEECALC"]["tests"])
    assert "FEECALC" not in qubo.read_text()
