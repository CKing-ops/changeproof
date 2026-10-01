# changeproof

Semantic change evidence engine. See `ROADMAP.md` for the build plan and `CLAUDE.md` for working rules.
Market: universal (`general`) is the main path and EU DORA (`eu-dora`) the strong second.

Focus: the link between what a change touches in the code and proof that nothing else changed
behaviour, in one evidence record per change. Both halves are proven for COBOL linkage
subprograms: impact (`tests/test_impact.py`) and behavioral equivalence outside the impact set,
joined by the impact statement's digest and checked by the policy gate (`tests/test_equivalence.py`,
`tests/test_gate.py`). Programs that read files, Db2 or CICS still show as untested until stubs exist
(**planned**). Neither half alone is new: CAST, OpenText and IBM ADDI do impact analysis, IBM
watsonx Code Assistant for Z tests equivalence for COBOL-to-Java translation, and Kosli keeps
tamper-evident change records. Sources and the full comparison are in `ROADMAP.md` (Positioning).

## Status

Weeks 1-11 (planned capabilities are labeled; proven ones cite their test):

- `changeproof init` writes a starter `changeproof.yaml` (`tests/test_cli.py`).
- `changeproof validate` checks a config against the schema (`tests/test_cli.py`).
- Market rules are a profile: `general` (default), `us-defense` or `eu-dora`, picked with
  `market:` in the config or `changeproof init --market` (`tests/test_markets.py`, `tests/test_egress.py`).
- Default configuration makes zero network calls (`tests/test_offline.py`).
- COBOL parser chosen: ANTLR4 Cobol85 parses 95.6% of the 503-program corpus (`docs/adr/001-parser.md`, `spike/results/summary.md`).
- COBOL adapter: preprocesses `COPY`/`REPLACING`/`REPLACE`/`EXEC`, parses, and emits IR entities with
  `file:line` provenance, including crypto-relevant calls (`tests/test_cobol_adapter.py`,
  `tests/test_cobol_exit_check.py`).
- Dependency graphs: calls, PERFORM, copybooks, files, Db2 tables and JCL, stored in SQLite, with
  every edge pointing at its statement and unresolved targets reported (`tests/test_graph.py`,
  `scripts/graph_corpus_run.py`). CICS transactions, screens and CSD datasets are included, and edges
  and shared data between configured components are marked (`tests/test_graph.py`).
- Field-level data flow: `MOVE`, `COMPUTE`, arithmetic, `READ INTO`, `WRITE FROM`, `STRING` and
  `UNSTRING` become `flows-to` edges with upstream/downstream lineage (`tests/test_cobol_flows.py`,
  `tests/test_lineage.py`).
- `changeproof change <commit or range>` prints who/what/when/where/how/why records from a local git
  repository, with requester, implementer and approver kept apart, an emergency flag and ticket IDs
  copied from the commit message (`tests/test_change.py`, `scripts/change_exit_check.py`).
- `changeproof impact <commit or range>` prints an impact predicate: changed entities, everything that
  depends on them with a confidence tier (definite, probable, possible) and the path that reached it,
  the systems that rely on them, a crypto flag and every gap (`tests/test_impact.py`,
  `scripts/impact_corpus_check.py`).
- Framework mapping: evidence mapped to SOC 2 and ISO/IEC 27001 first, then DORA and the ECB IT Risk
  Questionnaire, then the US profile, with each control's source and check status
  (`docs/framework-mapping.md`, `tests/test_frameworks.py`). Most control numbers are still
  **unverified** at source.
- Signed evidence: a signer interface owns all cryptography, with ECDSA P-384, ML-DSA-87 and LMS
  registered. `changeproof impact --key` signs the impact statement; `sign`, `release`, `verify`
  (offline) and `resign` (countersign without altering) work under the `hybrid`, `nist-pqc`, `cnsa2`
  and `classical-legacy` profiles. Tampering fails under every profile, and a hybrid signature still
  verifies when either algorithm is distrusted (`tests/test_signer.py`, `tests/test_release.py`,
  `tests/test_cli.py`). Production key custody and certified crypto modules: **planned** (Week 17).
- Policy gate: `changeproof gate <commit or range>` runs the rules named in `policy:` as OPA/Rego.
  `no-new-quantum-vulnerable-crypto` blocks a change that adds RSA, ECC, DSA or DH, read from the
  literals a crypto call is given. `high-criticality-needs-two-approvers` is also enforced.
  `--oscal` writes OSCAL 1.1.2 assessment results that validate against NIST's schema
  (`tests/test_gate.py`, `docs/adr/005-policy-gate-and-oscal.md`). A CI job template is in
  `docs/ci/changeproof-gate.yml`. `equivalence-required-outside-impact-set` blocks a behaviour change
  outside the impact set and warns about programs it cannot test (`tests/test_gate.py`,
  `tests/policies/`).
- Characterization tests: `changeproof characterize` runs a COBOL linkage subprogram under GnuCOBOL
  (locally, or in `docker/gnucobol` with networking off) on boundary inputs read from the program,
  traces which way each `IF`, `WHEN` and `PERFORM UNTIL` went, and writes a golden suite with every
  condition's `file:line`. On the three synthetic batch programs every one of the 21 conditions has
  tests both ways, suites are reproducible, and `--replay` catches a changed fee rate
  (`tests/test_characterize.py`, `docs/adr/006-characterization.md`). Programs that read files, Db2
  or CICS need stubs: **planned**.
- Behavioral equivalence: `changeproof equivalence <commit or range>` builds characterization tests
  from each program before the change, replays them after it, and prints a behavioral-equivalence
  predicate (signed with `--key`). By default it tests only programs outside the impact set and
  names the impact statement it used by digest. Programs it cannot test are listed with the reason,
  and the verdict is then inconclusive. Mutation check: the tests catch 19 of 20 seeded bugs (95%)
  and 8 of 10 held-out bugs (`tests/test_equivalence.py`, `scripts/mutation_check.py`,
  `docs/adr/007-equivalence.md`).
- Solver interface: `solve(problem, backend)` with the `classical` backend (OR-Tools CP-SAT and a
  greedy baseline). `quantum-sim` and `qpu` are reserved (**planned**), and a remote backend must pass
  the same egress rules as config validation or raise (`tests/test_solver.py`,
  `docs/adr/008-solver-interface.md`).
- Test selection: `changeproof select` picks the fewest characterization tests that cover an edit.
  On 30 seeded bugs the subsets catch exactly what the full suites catch (27), with 281 test runs
  instead of 517 (`tests/test_selection.py`, `scripts/selection_check.py`).
- Change-risk ranking: fan-in, criticality, churn and crypto-touch per program, each value citing
  the lines or commits it was counted from, ranked by a gradient-boosted baseline. It is trained on
  a seeded synthetic history, so it proves the pipeline, not accuracy on real incidents
  (`tests/test_risk.py`). Real defect history: **planned**.
- QUBO and Ising export of both problems, with names stripped; on small instances the QUBO minimum
  equals the classical optimum (`tests/test_solver.py`). `changeproof benchmark` stores quality,
  runtime, cost and a reproducibility digest per run in `benchmarks/runs/` (`tests/test_benchmark.py`).
- Java adapter: tree-sitter-java parses classes, methods, fields, calls and JCA crypto calls with
  `file:line` provenance; Java changes get the same graph, impact predicate and policy gate as COBOL.
  Six seeded changes match their hand-marked impact, and on 16 Apache Commons Lang commits every
  changed entity lies in a changed hunk and every graph edge cites its line
  (`tests/test_java_adapter.py`, `tests/test_java_impact.py`, `tests/test_java_corpus.py`,
  `docs/adr/009-java-adapter.md`). Running Java for equivalence tests: **planned**. Other
  languages: **planned**.
- Crypto-inventory evidence: **planned** (Week 16).

## Development

```sh
uv sync
uv run pytest
```

`changeproof gate` and its tests need OPA on the `PATH` (or `$CHANGEPROOF_OPA`), the same way
`change` and `impact` need git: `go install github.com/open-policy-agent/opa@v1.21.1`.
