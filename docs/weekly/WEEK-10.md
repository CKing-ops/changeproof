# Week 10: Optimization layer and solver interface

- Market: universal build (`general` main path, `eu-dora` strong second, `us-defense` kept passing)
- Branch: `week-10-solver`, built on `main` after Week 9 (PR #15)
- Date: 2026-10-01
- Status: exit check met

## Exit check

| Check | Result | Evidence |
|---|---|---|
| Selected subsets catch the same mutations as the full suite | **Met: 30 of 30 bugs agree** (both catch 27; both miss R2, H3, H6), for CP-SAT and for greedy | `tests/test_selection.py::test_exit_check_selected_subsets_catch_the_same_mutations_as_the_full_suite`; per-bug table in `docs/weekly/week10-selection.json` (`scripts/selection_check.py`) |
| QUBO export equivalent to the classical model on small instances | **Met** | Set cover: brute-force QUBO minimum equals the CP-SAT optimum and decodes to a valid cover on 25 or more random instances of up to 18 variables (`tests/test_solver.py::test_exit_check_cover_qubo_minimum_is_the_classical_optimum_on_small_instances`), and on the real selection problems small enough to enumerate (`tests/test_selection.py::test_the_selection_qubo_has_the_classical_minimum_where_brute_force_reaches`). Top-k: 30 random instances (`::test_exit_check_top_k_qubo_minimum_is_the_classical_choice`). Ising energy equals QUBO energy on every assignment (`::test_ising_form_gives_the_same_energy_for_every_assignment`) |

The three bugs neither catches are the Week 9 computed-field boundaries. Selection cannot do better
than the suite it selects from.

Test runs across the 30 bugs: full suites 517, CP-SAT 281, greedy 285. So selection saves 46%
of runs here, unevenly. 14 of the 30 bugs keep five tests or fewer. Six changes on RISKSCR's main
line keep 21 of 22, because every path passes through them and the rule keeps every path (ADR 008). CP-SAT never picks more than greedy
(`::test_cp_sat_picks_no_more_tests_than_greedy_and_fewer_than_the_full_suite`).

## Roadmap items

- [x] **Solver interface.** `solve(problem, backend, config)` with `classical` available, and
  `quantum-sim` and `qpu` registered but **planned** (`tests/test_solver.py::test_backends_are_classical_now_and_the_others_reserved`,
  `::test_reserved_backends_say_so`).
- [x] **Egress gate in the solver interface.** A remote backend runs `check_egress` first, the same
  function config validation uses (ADR 003, gate 2 now proven). All 20 market, classification and
  data-tier cases from `tests/test_egress.py` are run through the solver, with the config's own
  validation skipped so the solver's gate is what is tested
  (`::test_remote_backends_pass_the_egress_gate_or_raise`). Egress off, no config, or a problem that
  is not a QUBO each raise `EgressDenied`; local backends never read the egress settings.
- [x] **Problem 1, regression test selection.** Characterization suites now record the lines each
  test ran and the boundary points it sat on (golden suites regenerated). `changeproof select` reads
  a suite and the edited source, works out the changed lines and solves the minimum cover by CP-SAT,
  or greedy with `--greedy` (`tests/test_selection.py`). A first rule (each condition outcome next
  to the changed line) missed two bugs the full suite caught, R6 and I1; it was replaced before the
  exit check by "every path through the changed line" (ADR 008).
- [x] **Problem 2, change-risk ranking.** Per program: fan-in, criticality, churn and crypto-touch,
  read from the graph, the config and git history at a revision. Every value cites what it was
  counted from (`tests/test_risk.py::test_every_feature_value_cites_where_it_came_from`). A
  gradient-boosted classifier is trained on a **synthetic** history (seeded; the rule is in
  `src/changeproof/risk.py`). On the held-out 600 rows it scores AUC 0.7242, against 0.5957 for
  ranking by fan-in alone (`::test_the_gradient_boosted_baseline_is_scored_beside_a_fan_in_heuristic_and_reproduces`).
  The labels were generated from these same features, so this proves the pipeline and fixes the
  baseline for Week 19. It says nothing about real incidents.
- [x] **QUBO and Ising export** of both problems. The serialized QUBO holds indices and numbers only
  (`::test_serialized_qubo_carries_no_names_from_the_problem`); `changeproof select --qubo` writes
  it. The top-k review shortlist from the risk ranking exports the same way
  (`tests/test_risk.py::test_the_review_shortlist_qubo_picks_what_the_classical_top_k_picks`).
- [x] **Benchmark harness.** `changeproof benchmark` writes one file per run to `benchmarks/runs/`:
  greedy beside CP-SAT on four seeded sizes, the QUBO check where brute force reaches, the risk
  baseline beside fan-in, cost (0), versions and a digest over everything except timings
  (`tests/test_benchmark.py`). First run: `benchmarks/runs/20261001T111203Z-735d36633a6d.json`. At
  80 elements and 60 candidates CP-SAT proved an optimum of 22 against greedy's 24.

No core schema changed. Characterization suites gained `lines`, `boundaries` and `decision_line`;
suites are an engine file format, not a signed predicate. ADR 008 records the design; ADR 003 now
cites the solver gate's tests.

The whole suite passes with sockets blocked: 416 tests.

## Outside facts (project rule 6)

None new this week. Dependency licenses (OR-Tools, scikit-learn and what they pull in) are logged in
`docs/licenses.md` from each package's own metadata.

## Open issues

- **Selection is conservative on main-line changes.** Keeping every path is what made it agree with
  the full suite; data-flow slicing to drop paths that cannot see the change is **planned**.
- **Risk labels are synthetic.** Real defect or incident history per change is needed before any
  accuracy claim (**planned**).
- **Brute-force checks stop at 20 variables.** Equivalence of the QUBO with the classical model is
  shown on small instances only, as the roadmap asks.
- **The sanitizer is partial.** Names are stripped; variable-order shuffling, padding and the full
  "no source-derived strings" test are **planned** for Week 20.

## Decisions needed from the owner

None to merge. ADR 008 is proposed and goes in with this week, as the workflow allows.
