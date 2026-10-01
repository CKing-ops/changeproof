"""Solver interface (ROADMAP Week 10, ADR 008). Remote backends pass the ADR 003 egress gate first."""

from dataclasses import dataclass

from changeproof.config import Config
from changeproof.egress import REMOTE_BACKENDS, check_egress
from changeproof.markets import MARKETS
from changeproof.solver.classical import cp_sat_cover, greedy_cover, top_k
from changeproof.solver.problems import SetCover, Solution, TopK
from changeproof.solver.qubo import Ising, Qubo, brute_force, cover_qubo, to_ising, top_k_qubo

__all__ = ["BACKENDS", "Backend", "EgressDenied", "Ising", "Qubo", "SetCover", "Solution", "TopK", "brute_force",
           "cover_qubo", "egress_gate", "greedy_cover", "solve", "to_ising", "top_k_qubo"]


class EgressDenied(PermissionError):
    pass


@dataclass(frozen=True)
class Backend:
    name: str
    remote: bool
    available: bool


BACKENDS = {name: Backend(name, name in REMOTE_BACKENDS, name == "classical")
            for name in ("classical", "quantum-sim", "qpu")}


# PURPOSE: RAISES EGRESSDENIED UNLESS THE CONFIG LETS THIS BACKEND TAKE DATA OFF THE MACHINE
def egress_gate(backend: Backend, config: Config | None) -> None:
    if config is None:
        raise EgressDenied(f"the {backend.name} backend is remote and there is no config to allow egress")
    problems = check_egress(market=MARKETS[config.market], classification=config.system.classification,
                            backend=backend.name, egress=config.egress, crypto_profile=config.crypto.profile)
    if problems:
        raise EgressDenied("; ".join(problems))


# PURPOSE: SOLVES A PROBLEM ON A NAMED BACKEND; ONLY CLASSICAL RUNS TODAY
def solve(problem: SetCover | TopK | Qubo, backend: str = "classical", config: Config | None = None) -> Solution:
    if backend not in BACKENDS:
        raise ValueError(f"unknown backend {backend!r} ({' | '.join(BACKENDS)})")
    chosen = BACKENDS[backend]
    if chosen.remote:
        egress_gate(chosen, config)
        if not isinstance(problem, Qubo):
            raise EgressDenied("only a QUBO, which carries no names from the problem, may go to a remote backend")
    if not chosen.available:
        raise NotImplementedError(f"the {backend} backend is planned; its client would ship separately as "
                                  f"changeproof-{backend}, and its results beside the classical baseline")
    match problem:
        case SetCover():
            return cp_sat_cover(problem)
        case TopK():
            return top_k(problem)
    raise ValueError(f"the classical backend solves SetCover and TopK, not {type(problem).__name__}")
