# ADR 017: Public mainframe COBOL in a simulated bank

- Status: proposed. Asked for by the owner on 2026-11-24 ("Can the information found just be treated
  under our simulated bank ... so we can get better test results for what is missing? ... I do not have
  proprietary details for a live bank").
- Date: 2026-11-24
- Related: ADR 014 (bank simulation), ADR 013 (files and packed data), ADR 016 (diversified bank traffic)

## Context

The six simulated banks (ADR 014) run four tidy COBOL 85 programs written for the simulation. Real bank
code is CICS transactions over Db2 tables and VSAM files, with DCLGEN copybooks and schema kept in JCL.
None of that is in the simulation, so its scores say nothing about it. The owner has no bank code to
give us, and CLAUDE.md allows only public, open-source or synthetic code in `corpus/`.

Public candidates were surveyed by the project before this work. IBM's Cash Account service for its
Stock Trader sample is the best fit that can be committed: the upstream README describes a CICS/COBOL
program over Db2 for z/OS with VSAM as a cache
([README](https://github.com/IBMStockTrader/cash-account-cobol/blob/main/README.md)), and the repository's
LICENSE file is the Apache License 2.0
([LICENSE](https://github.com/IBMStockTrader/cash-account-cobol/blob/main/LICENSE), read 2026-11-24).
Other candidates from that survey (IBM GenApp under EPL-2.0, CBSA and zBANK with no license) are not
used here; licenses for those are as reported by the survey and **unverified** in this ADR.

## Decision

1. **Committed unmodified, pinned.** `corpus/ibm-cash-account/` holds upstream commit `c35db0d1`
   byte for byte (`SOURCE.md`, LICENSE kept, logged in `docs/licenses.md`).
2. **One bank runs it.** Prairie Ledger Bank (`general`, the main path in CLAUDE.md) carries the Cash
   Account beside its own four programs under `cash/` (`src/changeproof/banksim/public.py`), as
   component `cash-account` in its `changeproof.yaml`. The simulation adds a three-line CICS
   resource definition (`cash/csd/CASHACCT.csd`, program, a made-up transaction ID and the history
   file's dataset), since upstream ships none and a bank would have one.
3. **A catalogue with known truth, as in ADR 014.** Seven changes to the grafted code: two
   refactors (a message nobody reads, a name's capitalisation), three defects whose commit messages
   call them a tidy-up (credit sign flipped, history key built from the date, VSAM key length off by
   one) and two intended schema changes (wider balance in the DCLGEN copybook, wider column in the DDL).
   Each change also names the graph nodes a sound impact analysis must report (`reaches`).
4. **Scored like the main simulation, plus impact.** `scan` commits a change under a random approval
   path, runs the change record and the full-suite equivalence check, and scores behaviour, approvals
   and impact (`reached`, `partial`, `silent`). Each change is scanned against the same imported estate
   and kept off main, so the catalogue is repeatable. This runs beside the six-bank stream, not inside
   it: grafting into the running simulation would change every score at Prairie Ledger (point 2 under
   Consequences).
5. **The engine gaps the real code showed are fixed in the engine, not worked around.**
   - The parser rejected `CASH00` outright: a DCLGEN copybook ends its `EXEC SQL DECLARE TABLE` with
     `END-EXEC.`, and masking the block left a lone period in the data division
     (`corpus/ibm-cash-account/COBOL/DCLCASH.cpy:12`). A data-division block now takes its period with
     it (`preprocess.mask_exec_blocks`).
   - A change to in-stream input (SQL DDL under `DSNTIAD`, IDCAMS under `DEFINE CLUSTER`) produced no
     changed entities and no gap: a schema change was invisible. In-stream input is now part of its DD
     entity, and each `CREATE/ALTER/DROP TABLE` and `DEFINE CLUSTER` becomes a `jcl-define` entity with
     its `file:line` range (`graph/jcl.py`).
   - The impact walk enters a changed table or dataset definition at the `table:` or `dataset:` node and
     reaches every program, CICS file and job step that reads or writes it, as `definite`
     (`impact/walk.py`). No schema changed: `jcl-define` is a new entity kind and `defines` a new step
     name, both free strings in the impact predicate.

## Consequences

- **Behaviour on this code is not proven.** The engine cannot run CICS or Db2 programs yet; `CASH00`
  is listed untested with the reason, and every verdict at this bank is `inconclusive`, never
  `equivalent`. Stand-ins for CICS and Db2 remain **planned**.
- **One untested program makes every change at the bank inconclusive.** Full-suite equivalence
  (ADR 007) reports `inconclusive` when anything is untested, so a refactor to `INTACCR` that is proven
  at the other banks would be inconclusive here. That is the honest reading of the current rule;
  scoring per program is an open question for ADR 014's scorecard.
- **The catalogue is the limit.** Seven changes to one program and its JCL. CardDemo's Db2 programs
  name their DCLGEN members with `.dcl`, which the copybook search does not try, so their host
  variables never reach the IR; that is an open issue, not fixed here.
- The run is not part of the owner's daily simulation and does not touch its ledger or bundles.

## Evidence

- `tests/test_banksim_public.py`: the corpus is the pinned upstream under Apache-2.0; the host bank
  carries it unmodified beside its own programs; every catalogued change applies once; impact reaches
  what each of the seven changes must reach; a CICS defect is reported `inconclusive` with `CASH00`
  untested and never proven; a DDL change reaches `CASH00` through its table; approvals are scored from
  the change record.
- Six of the seven impact cases fail with the engine as it was before this ADR (checked by reverting
  `preprocess.py`, `jcl.py` and `walk.py`); only the capitalisation refactor, which must reach nothing,
  passed.
- `tests/test_cobol_preprocess.py::test_a_period_after_a_data_division_exec_block_goes_with_the_block`,
  `tests/test_jcl.py::test_instream_ddl_names_the_tables_it_defines_with_their_lines`,
  `tests/test_jcl.py::test_an_idcams_define_cluster_names_the_dataset_it_defines`,
  `tests/test_jcl.py::test_an_instream_edit_changes_the_dd_and_the_table_definition_entities`,
  `tests/test_impact.py::test_a_table_definition_change_in_ddl_reaches_every_program_that_uses_the_table`.

## First run (2026-11-24)

`uv run python scripts/bank_sim_public.py --out docs/weekly/banksim-cash-account.json`, all seven
changes, 203 seconds of scanning:

| | Result |
|---|---|
| Impact reached everything required | 6 of 6 changes that must reach something (the seventh requires nothing) |
| Silent changes (nothing changed, no gap) | 0 |
| Behaviour | 7 of 7 `inconclusive`, `CASH00` untested ("uses EXEC SQL ...; stand-ins for CICS, Db2 and IMS calls are planned"); 0 proven, 0 missed, 0 false alarms |
| Approvals | 3 flagged (one no-ticket, two emergency), 4 clean (governed); 0 missed, 0 false flags |
| Kept on main | 0 of 7 |

One noise finding: the capitalisation-only refactor (`BALANC-rate` to `BALANC-RATE`, `CASH00.cbl:256`)
is reported as 2 changed entities reaching 26 others. COBOL names ignore case, so a sound diff would
report nothing; open issue.
