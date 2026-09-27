# Week 3: dependency graphs

- Market: universal build, selling to DORA first
- Branch: `week-03-dependency-graphs`, built on `week-02-cobol-ir` (PR #4)
- Date: 2026-09-27
- Status: exit check met, including the owner-approved addition; waiting for owner review

## Exit check

| Check | Target | Result | Evidence |
|---|---|---|---|
| Every edge has provenance | all edges | **Met: 3,489 of 3,489 CardDemo edges carry `file:line`, and every one points at the statement that made it** (3,385 before the addition below) | `scripts/graph_corpus_run.py` → `docs/weekly/week03-carddemo-graph.json` (`edges_failing_check: []`); `tests/test_graph.py::test_every_edge_has_provenance`, `::test_every_edge_points_at_the_statement_it_came_from` |

An edge cannot be built without provenance (`Edge.provenance` is required). That alone would
make the check trivial, so `changeproof.graph.check.check_edges` goes further. It opens the cited
lines and requires the word that makes the edge to be there: `PERFORM` for a perform, the table
name for a table access, `//DDNAME` for a JCL binding, and so on
(`tests/test_graph.py::test_edge_check_catches_a_wrong_line` shows it catches a wrong line).

The first full run failed 4 of 3,385 edges. Each was an `EXEC SQL INCLUDE` split over two lines,
where the fact cited only the `EXEC SQL` line. Copybook facts now cite the whole statement, and
the rerun passed. That fix also made one Week 2 golden fact more exact: `COPY CSSETATY REPLACING`
in COTRTUPC now cites lines 1358-1361 instead of 1358.

The whole test suite passes: 211 tests with sockets blocked.

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

## Owner-approved addition: what CAST and OpenText show, and links between applications

The owner approved this addition on 2026-09-27 ("Add them", review thread), after the Week 0
competitor check found that CAST and OpenText already map programs, CICS transactions, Db2 tables,
files, batch jobs and JCL. Matching that is table stakes. The ECB IT Risk Questionnaire names
"unexpected interdependencies" as a cause of failed changes, so the graph now also marks where one
application reaches into another.

- [x] **CICS definitions.** `changeproof.graph.csd` reads CSD `DEFINE` statements. A transaction
  `starts` its program, and a CICS file maps to its dataset through `DSNAME`, which joins online
  file access to the batch jobs that use the same dataset
  (`tests/test_graph.py::test_cics_definitions_link_transactions_screens_and_datasets`).
- [x] **Screens and next transactions.** `EXEC CICS SEND/RECEIVE MAP` gives a `uses-screen` edge
  to the mapset, and `RETURN/START TRANSID` a `starts-transaction` edge (same test).
- [x] **Links between applications.** Each configured component owns the code under its path
  (longest path wins). An edge from one component's code to another's carries
  `crosses: [from, to]`, and a dataset, table or CICS file reached from two or more components
  carries `shared_by` (`::test_edges_between_components_are_marked`,
  `::test_resources_used_by_several_components_are_marked`).

CardDemo ships a base application and three optional extensions, so the run treats each as a
component (`docs/examples/carddemo.yaml`). The result:

| Interdependency | Count | Example |
|---|---|---|
| Extension copies a base copybook | 36 edges | 17 of them are authorization programs copying base copybooks |
| Extension runs base procedure code | 6 edges | transaction-type programs whose paragraphs come from base copybooks |
| Dataset or CICS file shared by components | 9 resources | `ACCTDAT` and its VSAM file are used by the base application, authorization and vsam-mq |

## CardDemo graph

44 programs, 48 JCL members and 4 CSD members give 1,418 nodes and 3,489 edges. Before the
addition above, 44 programs and 48 JCL members gave 1,369 nodes and 3,385 edges. The largest groups are 1,202
performs, 1,024 contains, 357 includes, 213 DD, 200 GO TO, 118 runs and 97 calls. There are 44
file-to-dataset bindings, which link 44 program files to the datasets their jobs give them.

251 of the original edges are unresolved. 223 point at IBM-supplied code, which is outside the
corpus. The other 28 are dynamic calls inside CardDemo whose target is only set at run time:

| Reason | Count | Most common targets |
|---|---|---|
| Copybook not found | 71 | CICS `DFHAID` and `DFHBMSCA`, MQ `CMQ*`, `SQLCA` |
| Step runs a program not in the code | 106 | `IDCAMS` (61), `IEFBR14`, `IEBGENER`, `SDSF`, `IKJEFT01`, `SORT` |
| Call to a program not in the code | 46 | `CEE3ABD` (Language Environment), MQ `MQOPEN`/`MQGET`/`MQPUT`/`MQCLOSE`, `COBDATFT` |
| Dynamic call with no `VALUE` | 28 | CICS `XCTL PROGRAM(CDEMO-TO-PROGRAM)`, set by `MOVE` at run time |

The addition leaves 6 more unresolved: transaction `CDV1` names program `COCRDSEC`, which CardDemo
does not ship, and 5 screens are sent through `CCARD-NEXT-MAPSET`, which is set by `MOVE`.

The graph database is written to `corpus/carddemo-graph.sqlite` (git-ignored).

## Open issues

- **System names are unresolved, not classified.** Tagging IBM-supplied programs and copybooks
  (CICS, MQ, LE, utilities) as `system` would leave only the 28 dynamic calls as real gaps.
- **Dynamic targets set by `MOVE`** need data-flow analysis. That fits Week 4's field-level lineage.
- JCL symbolic parameters (`&HLQ`) are kept as written, and concatenated DDs are not merged.
- Parsing speed is unchanged from Week 2: the full CardDemo graph takes about 1,300 CPU seconds.
  There is still no IR cache (no hashing outside the signer interface until Week 6).

## Decisions needed from the owner

1. Approve Week 3. PR #4 (Week 2) merges first; this PR then retargets to `main`.
