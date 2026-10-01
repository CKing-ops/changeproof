# changeproof

Semantic change evidence engine. See `ROADMAP.md` for the build plan and `CLAUDE.md` for working rules.
Market: universal (`general`) is the main path and EU DORA (`eu-dora`) the strong second.

Focus: the link between what a change touches in the code and proof that nothing else changed
behaviour, in one evidence record per change. The impact half is proven for COBOL
(`tests/test_impact.py`); the equivalence half is **planned** (Weeks 8-9), so the joined record is
**planned** too. Neither half alone is new: CAST, OpenText and IBM ADDI do impact analysis, IBM
watsonx Code Assistant for Z tests equivalence for COBOL-to-Java translation, and Kosli keeps
tamper-evident change records. Sources and the full comparison are in `ROADMAP.md` (Positioning).

## Status

Weeks 1-6 (planned capabilities are labeled; proven ones cite their test):

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
- Adapters for languages other than COBOL: **planned** (Java in Week 11; see `ROADMAP.md`).
- Equivalence and crypto-inventory evidence: **planned** (Weeks 9, 16).

## Development

```sh
uv sync
uv run pytest
```
