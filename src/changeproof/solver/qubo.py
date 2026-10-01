import itertools
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from changeproof.solver.problems import SetCover, TopK

BRUTE_FORCE_LIMIT = 22  # RENAME: MOST VARIABLES BRUTE FORCE WILL ENUMERATE


@dataclass(frozen=True)
class Qubo:
    variables: tuple[str, ...]
    linear: dict[int, float]
    quadratic: dict[tuple[int, int], float]  # RENAME: (I, J) WITH I < J TO ITS COEFFICIENT
    offset: float = 0.0

    # PURPOSE: ENERGY OF ONE 0/1 ASSIGNMENT
    def energy(self, bits: Sequence[int]) -> float:
        return (self.offset + sum(v * bits[i] for i, v in self.linear.items())
                + sum(v * bits[i] * bits[j] for (i, j), v in self.quadratic.items()))

    # PURPOSE: SERIALIZED FORM FOR A REMOTE SOLVER: INDICES ONLY, NO NAME FROM THE PROBLEM
    def to_json(self) -> dict:
        return {"variables": len(self.variables), "offset": self.offset,
                "linear": [[i, v] for i, v in sorted(self.linear.items())],
                "quadratic": [[i, j, v] for (i, j), v in sorted(self.quadratic.items())]}

    # PURPOSE: READS THE SERIALIZED FORM BACK, NAMING VARIABLES X0..XN
    @classmethod
    def from_json(cls, data: dict) -> "Qubo":
        return cls(tuple(f"x{i}" for i in range(data["variables"])), {i: v for i, v in data["linear"]},
                   {(i, j): v for i, j, v in data["quadratic"]}, data["offset"])


@dataclass(frozen=True)
class Ising:
    h: dict[int, float]
    j: dict[tuple[int, int], float]
    offset: float

    # PURPOSE: ENERGY OF ONE +1/-1 SPIN ASSIGNMENT
    def energy(self, spins: Sequence[int]) -> float:
        return (self.offset + sum(v * spins[i] for i, v in self.h.items())
                + sum(v * spins[a] * spins[b] for (a, b), v in self.j.items()))


class Builder:
    # PURPOSE: STARTS AN EMPTY QUBO OVER THE NAMED DECISION VARIABLES
    def __init__(self, names: Sequence[str]):
        self.variables = list(names)
        self.linear, self.quadratic, self.offset = defaultdict(float), defaultdict(float), 0.0

    # PURPOSE: ADDS A SLACK VARIABLE AND RETURNS ITS INDEX
    def slack(self, label: str) -> int:
        self.variables.append(label)
        return len(self.variables) - 1

    # PURPOSE: ADDS WEIGHT * (SUM OF COEF * X + CONSTANT)^2, USING X * X = X
    def square(self, terms: list[tuple[int, int]], constant: float, weight: float) -> None:
        for (i, a), (j, b) in itertools.combinations(terms, 2):
            self.quadratic[min(i, j), max(i, j)] += 2 * weight * a * b
        for i, a in terms:
            self.linear[i] += weight * (a * a + 2 * a * constant)
        self.offset += weight * constant * constant

    # PURPOSE: THE FINISHED QUBO, ZERO TERMS DROPPED
    def build(self) -> Qubo:
        return Qubo(tuple(self.variables), {i: v for i, v in self.linear.items() if v},
                    {k: v for k, v in self.quadratic.items() if v}, self.offset)


# PURPOSE: BINARY WEIGHTS WHOSE 0/1 SUMS REACH EXACTLY 0..TOP
def slack_weights(top: int) -> list[int]:
    weights = []
    while sum(weights) < top:
        weights.append(min(2 ** len(weights), top - sum(weights)))
    return weights


# PURPOSE: SET COVER AS A QUBO: COSTS PLUS A PENALTY FOR EACH UNCOVERED ELEMENT, SLACK BITS ABSORB OVER-COVER
def cover_qubo(problem: SetCover) -> tuple[Qubo, Callable[[Sequence[int]], tuple[str, ...]]]:
    names = sorted(problem.sets)
    built = Builder(names)
    penalty = sum(problem.costs.values()) + 1  # RENAME: MORE THAN ANY COVER COSTS, SO A GAP NEVER PAYS
    for i, n in enumerate(names):
        built.linear[i] += problem.costs[n]
    for e, element in enumerate(problem.universe):
        covering = [(i, 1) for i, n in enumerate(names) if element in problem.sets[n]]
        if not covering:
            raise ValueError(f"no candidate covers {element}")
        # sum(x) - 1 - slack = 0 holds for any cover count 1..len(covering)
        slack = [(built.slack(f"slack{e}.{b}"), -w) for b, w in enumerate(slack_weights(len(covering) - 1))]
        built.square(covering + slack, -1, penalty)
    return built.build(), lambda bits: tuple(n for i, n in enumerate(names) if bits[i])


# PURPOSE: TOP-K AS A QUBO: MINUS THE CHOSEN SCORES PLUS A PENALTY ON (CHOSEN - K)^2
def top_k_qubo(problem: TopK) -> tuple[Qubo, Callable[[Sequence[int]], tuple[str, ...]]]:
    names = sorted(problem.scores)
    built = Builder(names)
    for i, n in enumerate(names):
        built.linear[i] -= problem.scores[n]
    built.square([(i, 1) for i in range(len(names))], -problem.k, sum(map(abs, problem.scores.values())) + 1)
    return built.build(), lambda bits: tuple(n for i, n in enumerate(names) if bits[i])


# PURPOSE: ISING FORM OF A QUBO UNDER X = (1 - S) / 2
def to_ising(qubo: Qubo) -> Ising:
    h, j, offset = defaultdict(float), {}, qubo.offset
    for i, v in qubo.linear.items():
        offset += v / 2
        h[i] -= v / 2
    for (a, b), v in qubo.quadratic.items():
        offset += v / 4
        h[a] -= v / 4
        h[b] -= v / 4
        j[a, b] = v / 4
    return Ising(dict(h), j, offset)


# PURPOSE: EXACT MINIMUM OF A SMALL QUBO BY TRYING EVERY ASSIGNMENT; THE FIRST MINIMUM IN BINARY ORDER WINS
def brute_force(qubo: Qubo) -> tuple[float, tuple[int, ...]]:
    n = len(qubo.variables)
    if n > BRUTE_FORCE_LIMIT:
        raise ValueError(f"{n} variables is past the brute-force limit of {BRUTE_FORCE_LIMIT}")
    bits = (np.arange(2 ** n)[:, None] >> np.arange(n - 1, -1, -1)) & 1
    energy = np.full(2 ** n, qubo.offset)
    for i, v in qubo.linear.items():
        energy += v * bits[:, i]
    for (i, j), v in qubo.quadratic.items():
        energy += v * (bits[:, i] & bits[:, j])
    best = int(np.argmin(energy))
    return float(energy[best]), tuple(int(b) for b in bits[best])
