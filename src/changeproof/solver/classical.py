from ortools.sat.python import cp_model

from changeproof.solver.problems import SetCover, Solution, TopK

SEED = 0  # RENAME: CP-SAT RANDOM SEED; FIXED SO A RUN CAN BE REPRODUCED
WORKERS = 1  # RENAME: CP-SAT SEARCH THREADS; ONE KEEPS THE SEARCH ORDER DETERMINISTIC
TIME_LIMIT = 60.0  # RENAME: SECONDS BEFORE CP-SAT RETURNS ITS BEST SO FAR


# PURPOSE: CHEAPEST-PER-NEW-ELEMENT GREEDY COVER, THE BASELINE CP-SAT IS MEASURED AGAINST
def greedy_cover(problem: SetCover) -> Solution:
    left, chosen = set(problem.universe), []
    while left:
        best = min((n for n in sorted(problem.sets) if problem.sets[n] & left),
                   key=lambda n: problem.costs[n] / len(problem.sets[n] & left), default=None)
        if best is None:
            raise ValueError(f"no candidate covers {sorted(left)[0]}")
        chosen.append(best)
        left -= problem.sets[best]
    selection = tuple(sorted(chosen))
    return Solution(selection, sum(problem.costs[n] for n in selection), "classical", "greedy", False)


# PURPOSE: MINIMUM-COST COVER WITH CP-SAT
def cp_sat_cover(problem: SetCover) -> Solution:
    model = cp_model.CpModel()
    names = sorted(problem.sets)
    pick = {n: model.new_bool_var(n) for n in names}  # RENAME: CANDIDATE NAME TO ITS 0/1 VARIABLE
    for element in problem.universe:
        covering = [pick[n] for n in names if element in problem.sets[n]]
        if not covering:
            raise ValueError(f"no candidate covers {element}")
        model.add_bool_or(covering)
    model.minimize(sum(problem.costs[n] * pick[n] for n in names))
    # starting from the greedy cover means a timed-out search is never worse than the baseline
    start = set(greedy_cover(problem).selection)
    for n in names:
        model.add_hint(pick[n], n in start)
    solver = cp_model.CpSolver()
    solver.parameters.random_seed = SEED
    solver.parameters.num_workers = WORKERS
    solver.parameters.max_time_in_seconds = TIME_LIMIT
    status = solver.solve(model)
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        raise RuntimeError(f"CP-SAT found no cover ({solver.status_name(status)})")
    selection = tuple(n for n in names if solver.value(pick[n]))
    return Solution(selection, sum(problem.costs[n] for n in selection), "classical", "cp-sat",
                    status == cp_model.OPTIMAL)


# PURPOSE: THE K HIGHEST SCORES, TIES BROKEN BY NAME
def top_k(problem: TopK) -> Solution:
    ranked = sorted(problem.scores, key=lambda n: (-problem.scores[n], n))[:problem.k]
    selection = tuple(sorted(ranked))
    return Solution(selection, sum(problem.scores[n] for n in selection), "classical", "sort", True)
