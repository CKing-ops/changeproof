"""Week 10 benchmark harness: quality, runtime, cost and reproducibility, stored per run."""

import json

import pytest

from changeproof.benchmark import SIZES, run_benchmark, write_run
from changeproof.cli import main


@pytest.fixture(scope="module")
def found():
    return run_benchmark(seed=0)


def test_each_size_reports_greedy_beside_the_cp_sat_optimum(found):
    rows = found["selection"]
    assert [(r["elements"], r["candidates"]) for r in rows] == list(SIZES)
    for row in rows:
        assert row["cp-sat"]["optimal"] and row["cp-sat"]["objective"] <= row["greedy"]["objective"]
        assert row["cp-sat"]["seconds"] >= 0 and row["greedy"]["seconds"] >= 0
        assert row["qubo"]["variables"] >= row["candidates"]
    small = [r for r in rows if "brute_force" in r["qubo"]]
    assert small and all(r["qubo"]["brute_force"] == r["cp-sat"]["objective"] for r in small)


def test_no_backend_but_classical_ran_and_nothing_was_spent(found):
    assert found["backends"] == {"classical": "ran", "quantum-sim": "planned", "qpu": "planned"}
    assert found["cost"]["usd"] == 0
    assert found["risk"]["labels"].startswith("synthetic")


def test_results_reproduce_apart_from_timings():
    first, second = run_benchmark(seed=0, sizes=SIZES[:3]), run_benchmark(seed=0, sizes=SIZES[:3])
    assert first["digest"] == second["digest"] and first["selection"] != []
    assert run_benchmark(seed=1, sizes=SIZES[:3])["digest"] != first["digest"]


def test_every_run_is_kept_in_its_own_file(found, tmp_path, capsys):
    path = write_run(found, tmp_path)
    assert path.parent == tmp_path and json.loads(path.read_text())["seed"] == 0
    assert main(["benchmark", "--out", str(tmp_path / "runs")]) == 0
    written = list((tmp_path / "runs").glob("*.json"))
    assert len(written) == 1 and capsys.readouterr().out.strip().endswith(written[0].name)
