# Week 5: impact engine and framework mapping

- Market: universal build (`general` main path, `eu-dora` strong second)
- Branch: `week-05-control-mapping-6wpsyr`, built on `main` after Week 4 (PR #7) and the doc fixes (PR #9)
- Date: 2026-10-01
- Status: exit check met on both the seeded repository and CardDemo; most control numbers are
  still unverified at source (see "Source checks")

## Why this week matters

changeproof's evidence has two halves. The first is what a change touches in the code. The second
is proof that nothing outside that set changed behaviour. Week 5 builds the first half and fixes
the boundary that the second half (behavioral equivalence, Weeks 8-9, **planned**) will test
against. The framework mapping leads with that pairing and marks the equivalence half planned.

## Exit check

| Check | Target | Result | Evidence |
|---|---|---|---|
| Recall on seeded changes (hand-labelled, `general` fixture) | ≥95% | **Met: 117 of 117 (100%)**, and every confidence tier matches its label | `tests/test_impact.py::test_exit_check_recall_on_seeded_changes`, `::test_confidence_tiers_match_the_labels` |
| Recall on seeded CardDemo changes (text-search oracle) | ≥95% | **Met: 1,460 of 1,460 (100%)** across 65 seeds | `scripts/impact_corpus_check.py` → `docs/weekly/week05-carddemo-impact.json` |

### Seeded repository (`general`)

`tests/fixtures/impact/seed.py` builds a synthetic billing platform (seven COBOL programs, two
copybooks, two JCL jobs, a CSD extract and a `general` config) and makes eleven seeded commits:
a calculation edit, a copybook field, a crypto service swap, a JCL dataset change, an SQL edit, a
literal change, a new paragraph, a deleted program that is still called, a CICS record value, a
copybook constant, and a file move. `tests/fixtures/impact/expected.json` holds the impact a
reviewer would mark for each, with a tier, written by hand from the code before the engine ran.

One label was corrected after the first run: in "report open invoices only" the SQL statement
changed but the paragraph holding it did not (the IR keeps EXEC blocks out of paragraph text), so
the paragraph is impacted, not changed. The engine reported it; the label had missed it.

Also proven on this repository:

- nothing outside the labels is reported in the labelled kinds (`::test_nothing_outside_the_labels_is_reported_in_the_gate_kinds`);
- a file move impacts nothing (`::test_a_move_impacts_nothing`);
- every impacted entity has a chain of steps from a changed entity, each with provenance
  (`::test_every_impacted_entity_has_a_path_from_a_changed_entity`);
- the crypto flag is right for all eleven (`::test_crypto_flag`);
- reliant systems come from the config, citing its line (`::test_reliant_systems_come_from_the_config_with_their_line`);
- a call to a deleted program is reported in `unresolved` (`::test_a_call_to_a_removed_program_is_reported_unresolved`);
- the output validates against the impact predicate schema v0.1 and wraps in an in-toto statement
  (`::test_predicates_validate_and_wrap_in_a_statement`); no schema changed.

### CardDemo

Seeds: the first paragraph of every second program (22), the first 01-level item of every second
copybook a program copies (26), and the first DD of each step that runs a CardDemo program (17).
Seeds are entity-level changes, so this measures the walk; the diff from Week 4 is already proven.

The oracle does not use the engine's parser or graph. It reads the source text and finds, by
regular expression, callers (CALL, LINK, XCTL; a quoted literal of the name counts when the program
also has a dynamic call), copiers, JCL steps (EXEC PGM=, IKJEFT01 RUN PROGRAM, DFSRRC00 PARM) and
CSD transactions, closed over callers. It judges programs, steps, jobs, procs and transactions.

| Run | Recall | What it showed |
|---|---|---|
| First | 31.2% (455 of 1,460) | The menu dispatch `XCTL PROGRAM(CDEMO-MENU-OPT-PGMNAME(WS-OPTION))` was dropped (subscripted option), and targets set through constants or menu tables were not resolved. CSD was also not loaded by the script (`.CSD` uppercase), and the oracle named PROCs as jobs |
| After fixes | **100% (1,460 of 1,460)** | 379 found as definite, 1,081 as probable |

Fixes, each with a test written first:

- CICS options accept a subscripted data name (`tests/test_lineage.py::test_dynamic_targets_resolve_through_tables_and_moved_constants`).
- Dynamic targets resolve through `MOVE` chains (`MOVE LIT-MENUPGM TO CDEMO-TO-PROGRAM`) and through
  same-picture `VALUE`s in storage that an enclosing group `REDEFINES` (CardDemo's menu tables). Both
  are **probable**, and each edge cites the fact the target came from.
- JCL steps that run a program through TSO batch (`RUN PROGRAM`) or an IMS region (`DFSRRC00` PARM)
  get a `runs` edge citing that line (`tests/test_jcl.py::test_programs_run_through_tso_batch_and_ims_regions`,
  `tests/test_graph.py::test_steps_run_programs_through_tso_and_ims`).

The engine also reports 5,915 entities the oracle does not expect: 5,782 **possible** (shared
datasets, tables and CICS files the oracle does not model), 103 probable and 30 definite (mostly
jobs that reach a program through a PROC). These are not counted as errors, and precision is not
measured; see open issues.

Caveat: the oracle uses the same idea of impact (callers, closed transitively, including XCTL), so
it checks resolution, not the idea. CardDemo's screens all XCTL to the menu and the menu to every
screen, so most online seeds reach every online program, at the probable tier.

## Roadmap items

- [x] **`changeproof impact <commit or range>`** prints the impact predicate (`tests/test_cli.py::test_impact_prints_the_predicate_for_a_commit`).
  - **Confidence tiers.** definite (static dependencies, use of a changed data definition),
    probable (dynamic target resolved from a literal, a data value reaching a reader, a step whose
    input changed), possible (a table, CICS file or dataset an impacted program writes).
  - **Paths.** Each impacted entity lists the steps that reached it (`called-by`, `run-by`,
    `read-by`, `writes`, ...), each with `file:line`.
  - **Reliant systems/partners** from `relied_on_by` in the committed `changeproof.yaml`.
  - **Crypto flag** when a changed entity is a crypto call or the changed code contains one.
  - **Gaps** in `unresolved`: unanalyzed files, parse failures, calls to removed programs, and
    dynamic calls with no resolved target that may reach the impact set.
- [x] **Graph additions.** `uses-data` edges for data named in `EXEC CICS` (INTO, FROM, RIDFLD,
  COMMAREA, SET) and `EXEC SQL` host variables, with read or write; `flows-to` edges name their
  paragraph (`tests/test_impact.py::test_exec_statements_use_data_items`).
- [x] **`docs/framework-mapping.md`**, generated from `src/changeproof/frameworks.py`: `general`
  (SOC 2 CC8.1; ISO/IEC 27001 A.8.25, 8.28, 8.29, 8.32), then `eu-dora` (DORA, RTS 2024/1774
  Art. 16 and 17, ECB IT Risk Questionnaire Q23a and Q23c-e), then `us-defense`. Every row links its
  source and states its check status; every evidence cell cites a test or says **planned**
  (`tests/test_frameworks.py`). The `eu-dora` profile now names `ecb-itrq`.

## Source checks (project rule 6)

| Reference | Status | Source |
|---|---|---|
| RTS 2024/1774 Art. 16, Art. 17(1)(a)-(h), Art. 6 and 6(4), Art. 7, recital 9 | **checked 2026-10-01** | [EUR-Lex](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202401774) |
| ECB ITRQ 2026 Q23a, Q23c-e | checked 2026-09-27 (fact-check) | [ECB](https://www.bankingsupervision.europa.eu/activities/srep/2026/html/ssm.srep_ITRQ2026.en.pdf) |
| DORA Art. 9(4)(e), 28(3), 30 | unverified; RTS Art. 17(1) itself cites Art. 9(4)(e) | [EUR-Lex 2022/2554](https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32022R2554) (approval prompt timed out; the fetch returned the RTS page instead) |
| SOC 2 CC8.1 | unverified | [AICPA](https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022) (approval timed out) |
| ISO/IEC 27001:2022 A.8.25, 8.28, 8.29, 8.32 | unverified | Paid standard; a copy of the standard would settle all four |
| NIST SP 800-53 CM-3, CM-4, SC-12, SC-13; SP 800-218; CNSA 2.0; GDPR Chapter V | unverified | links in the mapping (approval timed out) |

Found while checking: Art. 17(1) also covers emergency changes ((f), (g)) and "the potential impact
of a change on existing ICT security measures" ((h)). Both are now mapped. Recital 9 does name
"threats from quantum advancements", as ADR 002 says.

The whole test suite passes with sockets blocked: 264 tests.

## Open issues

- **Precision is not measured.** The possible tier is broad on CardDemo because every program that
  writes a shared VSAM file reaches every job that touches it. Narrowing it needs file-level read
  and write modes per step and program (**planned**).
- **Lineage between programs.** `CALL ... USING` parameters and LINKAGE are still not followed at
  field level; impact crosses programs at program level only.
- **CSD changes are not diffed.** A changed `.csd` file is listed in `unresolved` as not analyzed.
- **Dynamic calls still unresolved** are listed in every impact that reaches a program, so a
  reviewer sees where the set may be incomplete.
- **Unverified control numbers** above, until the pages are approved or a copy of ISO/IEC 27001 is
  available.
- **Speed.** `impact` parses every program at the head commit. No parse cache until the Week 6 signer
  interface (owner decision, 2026-09-27).

## Decisions needed from the owner

None to merge. Approving the EUR-Lex (DORA), AICPA and NIST pages when they are requested, or a
copy of ISO/IEC 27001, would turn the remaining unverified rows into checked ones.
