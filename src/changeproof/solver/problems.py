from dataclasses import dataclass


@dataclass(frozen=True)
class SetCover:
    universe: tuple[str, ...]  # RENAME: ELEMENTS EVERY SELECTION MUST COVER
    sets: dict[str, frozenset[str]]  # RENAME: CANDIDATE NAME TO THE ELEMENTS IT COVERS
    costs: dict[str, int]  # RENAME: CANDIDATE NAME TO ITS INTEGER COST


@dataclass(frozen=True)
class TopK:
    scores: dict[str, float]
    k: int


@dataclass(frozen=True)
class Solution:
    selection: tuple[str, ...]
    objective: float
    backend: str
    method: str
    optimal: bool
