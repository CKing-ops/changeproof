# changeproof

Semantic change evidence engine. See `ROADMAP.md` for the build plan and `CLAUDE.md` for working rules.

## Status

Weeks 1-4 (planned capabilities are labeled; proven ones cite their test):

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
- Adapters for languages other than COBOL: **planned** (not yet scheduled; see `docs/adr/004-market-profiles.md`).
- Impact, equivalence and crypto-inventory evidence: **planned** (Weeks 5, 9, 16).

## Development

```sh
uv sync
uv run pytest
```
