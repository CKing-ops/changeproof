"""Week 10: the solver interface, its egress gate, the classical solvers and the QUBO/Ising export."""

import itertools
import json
import random

import pytest

from changeproof.config import Config, Crypto, Egress, System
from changeproof.solver import (BACKENDS, EgressDenied, Qubo, SetCover, TopK, brute_force, cover_qubo, egress_gate,
                                greedy_cover, solve, to_ising, top_k_qubo)
from test_egress import MATRIX


def cover(universe, sets, costs=None):
    return SetCover(universe=tuple(universe), sets={k: frozenset(v) for k, v in sets.items()},
                    costs=costs or {k: 1 for k in sets})


SMALL = cover("abcde", {"t1": "ab", "t2": "bc", "t3": "cde", "t4": "ae", "t5": "d"})


def random_cover(rng, elements, sets):
    universe = [f"e{i}" for i in range(elements)]
    found = {}
    for j in range(sets):
        found[f"t{j}"] = frozenset(e for e in universe if rng.random() < 0.4)
    for e in universe:  # every element coverable
        found[rng.choice(sorted(found))] |= {e}
    return cover(universe, found, {k: rng.randint(1, 3) for k in found})


def test_backends_are_classical_now_and_the_others_reserved():
    assert {name: (b.remote, b.available) for name, b in BACKENDS.items()} == {
        "classical": (False, True), "quantum-sim": (False, False), "qpu": (True, False)}


def test_classical_cover_is_the_cp_sat_optimum_and_greedy_is_a_feasible_baseline():
    found = solve(SMALL, "classical")
    assert found.backend == "classical" and found.method == "cp-sat"
    assert found.optimal and found.objective == 2
    assert set().union(*(SMALL.sets[t] for t in found.selection)) == set(SMALL.universe)
    greedy = greedy_cover(SMALL)
    assert set().union(*(SMALL.sets[t] for t in greedy.selection)) == set(SMALL.universe)
    assert greedy.objective >= found.objective


def test_classical_solutions_are_reproducible():
    rng = random.Random(7)
    problem = random_cover(rng, 30, 25)
    first, second = solve(problem, "classical"), solve(problem, "classical")
    assert first.selection == second.selection and first.objective == second.objective


def test_top_k_picks_the_highest_scores():
    found = solve(TopK(scores={"a": 0.2, "b": 0.9, "c": 0.5, "d": 0.7}, k=2), "classical")
    assert found.selection == ("b", "d")


def test_reserved_backends_say_so():
    with pytest.raises(NotImplementedError, match="planned"):
        solve(SMALL, "quantum-sim")
    with pytest.raises(ValueError, match="unknown backend"):
        solve(SMALL, "annealer")


CRYPTO = Crypto.model_construct(profile="hybrid", signing=["ecdsa-p384"], release_signing="ecdsa-p384", hash="sha-384")


def config_for(market, classification, tier, extra):
    # model_construct skips config validation, so the solver's own gate is what is tested
    egress = Egress.model_construct(**(Egress().model_dump() | {"allowed": True, "data_tier": tier,
                                                                "approved_vendors": ["ibm-quantum"]} | extra))
    system = System.model_construct(name="s", owner="o", classification=classification)
    return Config.model_construct(market=market, system=system, egress=egress,
                                  crypto=CRYPTO)


@pytest.mark.parametrize(("market", "classification", "tier", "extra", "allowed"), MATRIX)
def test_remote_backends_pass_the_egress_gate_or_raise(market, classification, tier, extra, allowed):
    config = config_for(market, classification, tier, extra)
    qubo, _ = cover_qubo(SMALL)
    if allowed:
        egress_gate(BACKENDS["qpu"], config)
        with pytest.raises(NotImplementedError, match="changeproof-qpu"):
            solve(qubo, "qpu", config)
    else:
        with pytest.raises(EgressDenied):
            solve(qubo, "qpu", config)


def test_a_remote_backend_with_egress_off_or_no_config_is_denied():
    qubo, _ = cover_qubo(SMALL)
    with pytest.raises(EgressDenied, match="egress.allowed is false"):
        solve(qubo, "qpu", Config.model_construct(**{k: f.default for k, f in Config.model_fields.items()
                                                     if not f.is_required()} | {"crypto": CRYPTO, "system": System.model_construct(
                                                         name="s", owner="o", classification="internal")}))
    with pytest.raises(EgressDenied, match="no config"):
        solve(qubo, "qpu")


def test_only_a_qubo_may_go_to_a_remote_backend():
    config = config_for("general", "public", "public", {})
    with pytest.raises(EgressDenied, match="only a QUBO"):
        solve(SMALL, "qpu", config)


def test_local_backends_never_consult_egress():
    restricted = config_for("general", "restricted", "customer", {})
    assert solve(SMALL, "classical", restricted).objective == 2


def test_exit_check_cover_qubo_minimum_is_the_classical_optimum_on_small_instances():
    rng = random.Random(10)
    checked = 0
    for _ in range(40):
        problem = random_cover(rng, rng.randint(2, 5), rng.randint(2, 6))
        qubo, decode = cover_qubo(problem)
        if len(qubo.variables) > 18:
            continue
        energy, bits = brute_force(qubo)
        selection = decode(bits)
        assert set().union(*(problem.sets[t] for t in selection)) == set(problem.universe)
        assert energy == sum(problem.costs[t] for t in selection) == solve(problem, "classical").objective
        checked += 1
    assert checked >= 25


def test_exit_check_top_k_qubo_minimum_is_the_classical_choice():
    rng = random.Random(11)
    for _ in range(30):
        n = rng.randint(2, 10)
        scores = {f"c{i}": rng.randint(1, 100) / 100 for i in range(n)}
        problem = TopK(scores=scores, k=rng.randint(1, n))
        qubo, decode = top_k_qubo(problem)
        _, bits = brute_force(qubo)
        chosen = decode(bits)
        assert len(chosen) == problem.k
        assert sum(scores[c] for c in chosen) == pytest.approx(
            sum(scores[c] for c in solve(problem, "classical").selection))


def test_ising_form_gives_the_same_energy_for_every_assignment():
    qubo, _ = cover_qubo(cover("abc", {"t1": "ab", "t2": "bc", "t3": "c"}))
    ising = to_ising(qubo)
    for bits in itertools.product((0, 1), repeat=len(qubo.variables)):
        spins = [1 - 2 * b for b in bits]  # x = (1 - s) / 2
        assert ising.energy(spins) == pytest.approx(qubo.energy(bits))


def test_serialized_qubo_carries_no_names_from_the_problem():
    problem = cover(["branch:FEECALC.MAIN-PARA#1:true"], {"FEECALC-03": ["branch:FEECALC.MAIN-PARA#1:true"]})
    qubo, _ = cover_qubo(problem)
    text = json.dumps(qubo.to_json())
    assert "FEECALC" not in text and "branch" not in text
    assert Qubo.from_json(json.loads(text)).energy([1]) == qubo.energy([1])
