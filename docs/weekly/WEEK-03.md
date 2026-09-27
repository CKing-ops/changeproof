# Week 3: dependency graphs

- Market: universal build, selling to DORA first
- Branch: `week-03-dependency-graphs`, built on `week-02-cobol-ir` (PR #4)
- Date: 2026-09-27
- Status: exit check met; waiting for owner review

## Exit check

| Check | Target | Result | Evidence |
|---|---|---|---|
| Every edge has provenance | all edges | **Met: 3,385 of 3,385 CardDemo edges carry `file:line`, and every one points at the statement that made it** | `scripts/graph_corpus_run.py` → `docs/weekly/week03-carddemo-graph.json` (`edges_failing_check: []`); `tests/test_graph.py::test_every_edge_has_provenance`, `::test_every_edge_points_at_the_statement_it_came_from` |

An edge cannot be built without provenance (`Edge.provenance` is required). That alone would
make the check trivial, so `changeproof.graph.check.check_edges` goes further. It opens the cited
lines and requires the word that makes the edge to be there: `PERFORM` for a perform, the table
name for a table access, `//DDNAME` for a JCL binding, and so on
(`tests/test_graph.py::test_edge_check_catches_a_wrong_line` shows it catches a wrong line).

The first full run failed 4 of 3,385 edges. Each was an `EXEC SQL INCLUDE` split over two lines,
where the fact cited only the `EXEC SQL` line. Copybook facts now cite the whole statement, and
the rerun passed. That fix also made one Week 2 golden fact more exact: `COPY CSSETATY REPLACING`
in COTRTUPC now cites lines 1358-1361 instead of 1358.

The whole test suite passes: 208 tests with sockets blocked.

## Roadmap items

- [x] **Call graph.** `CALL` (static, or dynamic through a data item's `VALUE`), `EXEC CICS LINK`
  and `XCTL` (`tests/test_graph.py::test_calls_resolve_through_value_clauses_and_cics`).
- [x] **PERFORM graph.** `PERFORM` (with `THRU` ranges) and `GO TO`, preferring a paragraph in the
  caller's own section (`::test_perform_edges_include_thru_ranges`). The IR now has `perform` and
  `goto` facts (`tests/test_cobol_adapter.py::test_perform_thru_and_go_to`).
- [x] **Copybook graph.** Program to copybook, including `EXEC SQL INCLUDE`.
- [x] **File and table graph.** `SELECT` files, Db2 tables read or written in `EXEC SQL`, and CICS
  file commands (`::test_copybook_file_and_table_edges`, `::test_sql_table_references`).
- [x] **JCL graph.** Job, step, program, procedure and dataset, and a `binds` edge from a
  program's file to the dataset its DD statement names (`tests/test_jcl.py`,
  `::test_jcl_edges_bind_program_files_to_datasets`).
- [x] **SQLite and NetworkX.** `save_graph` / `load_graph` round-trip (`::test_sqlite_round_trip`);
  `Graph.to_networkx()` for traversals (`::test_networkx_view_matches_the_edge_list`).
- [x] **Unresolved edges reported.** An edge to anything outside the analyzed code points at an
  `unresolved:` node and carries the reason (`::test_unresolved_edges_are_reported_with_a_reason`).
- [x] **Config metadata on nodes.** A component's id, criticality, data stores and dependents are
  copied onto the program nodes under its path. The test uses an `eu-dora` config
  (`::test_component_config_is_on_program_nodes`).

## CardDemo graph

44 programs and 48 JCL members give 1,369 nodes and 3,385 edges. The largest groups are 1,202
performs, 1,024 contains, 357 includes, 213 DD, 200 GO TO, 118 runs and 97 calls. There are 44
file-to-dataset bindings, which link 44 program files to the datasets their jobs give them.

251 edges are unresolved, and every one points at IBM-supplied code, which is outside the corpus:

| Reason | Count | Most common targets |
|---|---|---|
| Copybook not found | 71 | CICS `DFHAID` and `DFHBMSCA`, MQ `CMQ*`, `SQLCA` |
| Step runs a program not in the code | 106 | `IDCAMS` (61), `IEFBR14`, `IEBGENER`, `SDSF`, `IKJEFT01`, `SORT` |
| Call to a program not in the code | 46 | `CEE3ABD` (Language Environment), MQ `MQOPEN`/`MQGET`/`MQPUT`/`MQCLOSE`, `COBDATFT` |
| Dynamic call with no `VALUE` | 28 | CICS `XCTL PROGRAM(CDEMO-TO-PROGRAM)`, set by `MOVE` at run time |

The graph database is written to `corpus/carddemo-graph.sqlite` (git-ignored).

## Open issues

- **System names are unresolved, not classified.** Tagging IBM-supplied programs and copybooks
  (CICS, MQ, LE, utilities) as `system` would leave only the 28 dynamic calls as real gaps.
- **Dynamic targets set by `MOVE`** need data-flow analysis. That fits Week 4's field-level lineage.
- The CICS file names (`cics-file:`) are not yet mapped to datasets through the CSD
  (`app/csd/CARDDEMO.CSD`).
- JCL symbolic parameters (`&HLQ`) are kept as written, and concatenated DDs are not merged.
- Parsing speed is unchanged from Week 2: the full CardDemo graph takes about 1,300 CPU seconds.
  There is still no IR cache (no hashing outside the signer interface until Week 6).

## Decisions needed from the owner

1. Approve Week 3. PR #4 (Week 2) merges first; this PR then retargets to `main`.
