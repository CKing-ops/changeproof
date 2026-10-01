# ADR 008: Solver interface and the two optimization problems

- Status: proposed (Week 10). The owner's workflow merges each week once its exit check passes, so
  this stands until the owner says otherwise.
- Date: 2026-10-01
- Related: ROADMAP.md Week 10 (and Weeks 18-20, which build on it), ADR 003 (egress), ADR 006
  (characterization), ADR 007 (equivalence)

## Context

Week 10 adds an optimization layer: pick the fewest tests that still cover a change, and rank
programs by change risk. The roadmap wants both solvable classically now and exportable for
quantum backends later, with the egress gate in place before any quantum code exists.

## Decision

1. **One entry point.** `changeproof.solver.solve(problem, backend, config)` takes a `SetCover`,
   `TopK` or `Qubo`. Backends are a registry: `classical` (local, available), `quantum-sim` (local,
   **planned**, Week 18) and `qpu` (remote, **planned**, Week 20). A reserved backend raises
   `NotImplementedError`; an unknown one raises `ValueError`.
2. **The egress gate runs first.** For a backend flagged remote, `solve` calls `check_egress` from
   ADR 003 with the config's market, classification, egress and crypto profile, and raises
   `EgressDenied` on any rule, on a missing config, or on anything but a QUBO. Local backends never
   read the egress settings.
3. **Classical methods.** Set cover uses OR-Tools CP-SAT with a fixed seed and one search thread,
   so a run can be repeated exactly. It starts from the greedy cover, so a search cut short by the
   60-second limit is never worse than greedy, and the result says whether optimality was proven.
   Greedy (cheapest cost per newly covered element) is kept as the baseline. Top-k is a sort.
4. **Test selection is a set cover over obligations read from the suite.** Each test in a
   characterization suite now records the lines it ran and the boundary points it sat on. For the
   lines a change touches in the base source:
   - a changed condition needs both its outcomes and every value the full suite tried on the input
     fields the condition names;
   - every changed line needs every path (set of condition outcomes) the full suite took through it.
   A `WHEN` is traced on its `EVALUATE` line, so that line stands in for it. The path rule came
   after a first version that asked only for each condition outcome alongside the changed line:
   that version missed two seeded bugs the full suite caught (R6 and I1), because the value that
   exposed them came from a particular path.
5. **Change risk is a classical baseline on four graph features.** Fan-in (edges into the program
   from other files), criticality (the component's level in the config), churn (commits that touched
   the file up to the revision) and crypto-touch (`uses-crypto` edges in the file). Each value keeps
   the lines or commits it was counted from. A gradient-boosted classifier (scikit-learn, fixed seed)
   is trained on a seeded synthetic history whose rule is stated in `src/changeproof/risk.py`. There
   is no real defect history yet, so the model's accuracy says nothing about real incidents; it fixes
   the pipeline and the baseline that Week 19 compares against.
6. **QUBO and Ising export.** Set cover becomes costs plus a penalty per element, with binary slack
   bits so that any cover count from 1 up keeps the penalty at zero; the penalty weight is one more
   than all costs together, so leaving an element uncovered never pays. Top-k becomes minus the
   chosen scores plus a penalty on (chosen - k)². The Ising form uses x = (1 - s) / 2. The serialized
   QUBO holds indices and numbers only.
7. **Benchmarks are stored per run.** `changeproof benchmark` writes one JSON file per run under
   `benchmarks/runs/`: greedy and CP-SAT on seeded instances (objective, proven optimal, seconds),
   the QUBO minimum where brute force reaches, the risk baseline's AUC beside fan-in alone, cost
   (zero: nothing left the machine), versions, and a digest over everything except timings.

## Consequences

- Selection keeps every path through a change. On a program whose main line every run passes
  through (RISKSCR), a change to that line keeps almost the whole suite. Tighter selection needs
  data-flow slicing (**planned**).
- Large random cover instances can be hard for one-thread CP-SAT. The default benchmark sizes stop
  at 80 elements and 60 candidates, where it still proves optimality; past that the 60-second limit
  can be hit, and the benchmark then reports `optimal: false` rather than hiding it. Real selection
  problems in the corpus are small (at most 22 tests).
- Brute force checks the QUBO only up to 20 variables, so equivalence with the classical model is
  shown on small instances, as the roadmap asks, and not beyond.
- Labels for change risk must come from real history before any accuracy claim (**planned**).
