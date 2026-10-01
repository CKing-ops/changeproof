"""Regression test selection (ROADMAP Week 10, problem 1): the fewest tests that still cover a change."""

import difflib
import re

from changeproof.solver import SetCover, Solution, greedy_cover, solve


# PURPOSE: BASE-SOURCE LINE NUMBERS AN EDIT REPLACES OR DELETES; AN INSERTION TOUCHES THE LINES EITHER SIDE
def changed_lines(base: str, head: str) -> set[int]:
    old = base.splitlines()
    found = set()
    for tag, i1, i2, _, _ in difflib.SequenceMatcher(None, old, head.splitlines(), autojunk=False).get_opcodes():
        if tag in ("replace", "delete"):
            found.update(range(i1 + 1, i2 + 1))
        elif tag == "insert":
            found.update(n for n in (i1, i1 + 1) if 1 <= n <= len(old))
    return found


# PURPOSE: WHAT EACH TEST CONTRIBUTES TOWARDS COVERING A CHANGE
def obligations(suite: dict, lines: set[int]) -> dict[str, frozenset[str]]:
    # a changed condition needs both outcomes and every value the full suite tried on the fields it names;
    # a changed line needs every path the full suite took through it
    changed = {c["id"]: c["decision_line"] for c in suite["conditions"] if c["provenance"]["line"] in lines}
    names = {c["id"]: {f["name"] for f in suite["fields"] if re.search(rf"(?<![\w-]){re.escape(f['name'])}(?![\w-])",
                                                                       c["condition"])}
             for c in suite["conditions"] if c["id"] in changed}  # RENAME: CHANGED CONDITION TO THE FIELDS IT NAMES
    # a WHEN is traced on its EVALUATE line, so a run reaches a changed WHEN through that line
    traced = lines | set(changed.values())  # RENAME: CHANGED LINES AS THE TRACE RECORDS THEM
    found = {}
    for test in suite["tests"]:
        through = traced.intersection(test["lines"])
        needs = {f"{c['condition']}={c['outcome']}" for c in test["covers"] if c["condition"] in changed}
        needs |= {f"{c}@{name}={test['input'][name]}" for c in {c["condition"] for c in test["covers"]} & changed.keys()
                  for name in names[c]}
        path = " ".join(f"{c['condition']}={c['outcome']}" for c in test["covers"])  # RENAME: OUTCOMES THIS RUN TOOK
        needs |= {f"line {n}: {path}" for n in through}
        if needs:
            found[test["id"]] = frozenset(needs)
    return found


# PURPOSE: TEST SELECTION FOR A CHANGE AS A UNIT-COST SET COVER
def selection_problem(suite: dict, lines: set[int]) -> SetCover:
    sets = obligations(suite, lines)
    return SetCover(universe=tuple(sorted(set().union(*sets.values()))), sets=sets, costs=dict.fromkeys(sets, 1))


# PURPOSE: THE TESTS TO RUN FOR A CHANGE, BY CP-SAT (MINIMUM) OR GREEDY (BASELINE)
def select_tests(suite: dict, lines: set[int], method: str = "cp-sat") -> Solution:
    problem = selection_problem(suite, lines)
    if not problem.universe:
        return Solution((), 0, "classical", method, True)
    return greedy_cover(problem) if method == "greedy" else solve(problem)


# PURPOSE: A COPY OF A SUITE KEEPING ONLY THE NAMED TESTS
def subset(suite: dict, ids: tuple[str, ...]) -> dict:
    return suite | {"tests": [t for t in suite["tests"] if t["id"] in ids]}
