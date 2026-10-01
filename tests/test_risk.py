"""Week 10 problem 2: change-risk ranking from graph features, with a gradient-boosted baseline."""

import importlib.util
from pathlib import Path

import pytest

from changeproof.risk import FEATURES, evaluate, rank, review_problem, risk_features, synthetic_history, train
from changeproof.solver import brute_force, solve, top_k_qubo

HERE = Path(__file__).resolve().parent

_spec = importlib.util.spec_from_file_location("risk_seed", HERE / "fixtures" / "impact" / "seed.py")
seeds = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(seeds)


@pytest.fixture(scope="module")
def billing(tmp_path_factory):
    root = tmp_path_factory.mktemp("risk") / "repo"
    shas = dict(seeds.seed(root))
    return root, shas


@pytest.fixture(scope="module")
def programs(billing):
    root, shas = billing
    return {p["program"]: p for p in risk_features(root, shas["customer-tier-field"], ["copy"])}


def test_features_are_read_from_the_graph_and_history_at_a_revision(programs):
    assert FEATURES == ("fan_in", "criticality", "churn", "crypto_touch")
    assert set(programs) == {"AUDLOG", "CUSTUPD", "INVMAIN", "INVONL", "INVRPT", "INVSIGN", "TAXCALC"}
    assert programs["TAXCALC"]["features"] == {"fan_in": 2, "criticality": 3, "churn": 2, "crypto_touch": 0}
    assert programs["INVSIGN"]["features"]["crypto_touch"] == 1
    assert programs["INVMAIN"]["features"]["fan_in"] == 1  # run by its JCL step


def test_every_feature_value_cites_where_it_came_from(billing, programs):
    root, _ = billing
    taxcalc = programs["TAXCALC"]["evidence"]
    assert sorted(f"{p['file']}:{p['line']}" for p in taxcalc["fan_in"]) == [
        "src/batch/INVMAIN.cbl:31", "src/online/INVONL.cbl:13"]
    assert taxcalc["criticality"][0]["file"] == "changeproof.yaml"
    assert [p["file"].split("/")[0] for p in taxcalc["churn"]] == ["git-commit", "git-commit"]
    assert [f"{p['file']}:{p['line']}" for p in programs["INVSIGN"]["evidence"]["crypto_touch"]] == [
        "src/batch/INVSIGN.cbl:10"]
    for program in programs.values():
        assert program["provenance"]["file"].endswith(".cbl")
        for name, value in program["features"].items():
            cited = program["evidence"][name]
            assert len(cited) == value or (name == "criticality" and len(cited) <= 1), (program["program"], name)


def test_synthetic_history_is_labelled_as_such_and_reproducible():
    first, second = synthetic_history(200, seed=3), synthetic_history(200, seed=3)
    assert first.source.startswith("synthetic")
    assert (first.x == second.x).all() and (first.y == second.y).all()
    assert first.x.shape == (200, len(FEATURES))


def test_the_gradient_boosted_baseline_is_scored_beside_a_fan_in_heuristic_and_reproduces():
    found = evaluate(seed=0)
    assert found == evaluate(seed=0)
    assert found["labels"].startswith("synthetic")
    assert set(found["auc"]) == {"gradient-boosted", "fan-in"}
    assert found["auc"]["gradient-boosted"] > found["auc"]["fan-in"]


def test_ranking_scores_every_program_and_keeps_its_evidence(programs):
    ranked = rank(train(synthetic_history(500, seed=0)), list(programs.values()))
    assert sorted(r["program"] for r in ranked) == sorted(programs)
    assert [r["score"] for r in ranked] == sorted((r["score"] for r in ranked), reverse=True)
    assert all(r["evidence"] == programs[r["program"]]["evidence"] for r in ranked)
    assert ranked == rank(train(synthetic_history(500, seed=0)), list(programs.values()))


def test_the_review_shortlist_qubo_picks_what_the_classical_top_k_picks(programs):
    ranked = rank(train(synthetic_history(500, seed=0)), list(programs.values()))
    problem = review_problem(ranked, 3)
    qubo, decode = top_k_qubo(problem)
    _, bits = brute_force(qubo)
    chosen = solve(problem).selection
    assert sum(problem.scores[p] for p in decode(bits)) == pytest.approx(sum(problem.scores[p] for p in chosen))
    assert sorted(chosen) == sorted(r["program"] for r in ranked[:3])
