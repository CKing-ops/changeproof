# Week 2: intermediate representation (COBOL adapter)

- Market: universal build, selling to DORA first
- Branch: `week-02-cobol-ir`, on `main` after the universal Week 1 merged (#3)
- Date: 2026-09-27
- Status: exit check met; waiting for owner review

## Exit check

| Check | Target | Result | Evidence |
|---|---|---|---|
| Hand-checked facts | 20 facts, 100% correct provenance | **Met: 20 of 20 correct** | Table below; `tests/test_cobol_exit_check.py` keeps them true |

The whole test suite passes: 181 tests with sockets blocked.

### The 20 facts

`scripts/sample_facts.py` drew them from three CardDemo programs with a fixed seed, taking every
kind of fact in turn: a batch program (CBACT01C), a CICS program (COSGN00C), and a CICS and Db2
program that uses `COPY ... REPLACING` (COTRTUPC). For each one I opened the cited file at the
cited line and checked that the fact starts there, ends at the cited end line, and sits under the
parent named in its id (group items, paragraphs). Six of them live in copybooks, and all six
point at the copybook rather than at the program that copied it.

| # | Fact | Provenance | Source line (columns 8-72) | Hand check |
|---|---|---|---|---|
| 1 | `call:CBACT01C.9999-ABEND-PROGRAM.CEE3ABD#1` | `corpus/carddemo/app/cbl/CBACT01C.cbl:410` | `CALL 'CEE3ABD' USING ABCODE, TIMING.` | correct |
| 2 | `condition:COTRTUPC.CC-WORK-AREAS.CC-WORK-AREA.CCARD-AID.CCARD-AID-PA1` | `corpus/carddemo/app/cpy/CVCRD01Y.cpy:6` | `88  CCARD-AID-PA1                  VALUE 'PA1  '.` | correct |
| 3 | `copybook:COSGN00C.CSMSG01Y#1` | `corpus/carddemo/app/cbl/COSGN00C.cbl:54` | `COPY CSMSG01Y.` | correct |
| 4 | `data:COTRTUPC.ABEND-DATA.ABEND-CULPRIT` | `corpus/carddemo/app/cpy/CSMSG02Y.cpy:24-25` | `05  ABEND-CULPRIT                         PIC X(8)` | correct |
| 5 | `exec-cics:COTRTUPC.1100-RECEIVE-MAP#1` | `corpus/carddemo/app/app-transaction-type-db2/cbl/COTRTUPC.cbl:642-647` | `EXEC CICS RECEIVE MAP(LIT-THISMAP)` | correct |
| 6 | `exec-sql:COTRTUPC.9600-WRITE-PROCESSING#1` | `corpus/carddemo/app/app-transaction-type-db2/cbl/COTRTUPC.cbl:1544-1548` | `EXEC SQL` | correct |
| 7 | `file:CBACT01C.ACCTFILE-FILE` | `corpus/carddemo/app/cbl/CBACT01C.cbl:29-33` | `SELECT ACCTFILE-FILE ASSIGN TO ACCTFILE` | correct |
| 8 | `paragraph:COTRTUPC.9600-WRITE-PROCESSING-EXIT` | `corpus/carddemo/app/app-transaction-type-db2/cbl/COTRTUPC.cbl:1593-1595` | `9600-WRITE-PROCESSING-EXIT.` | correct |
| 9 | `program:CBACT01C` | `corpus/carddemo/app/cbl/CBACT01C.cbl:22-426` | `IDENTIFICATION DIVISION.` | correct |
| 10 | `call:CBACT01C.1300-POPUL-ACCT-RECORD.COBDATFT#1` | `corpus/carddemo/app/cbl/CBACT01C.cbl:231` | `CALL 'COBDATFT'       USING CODATECN-REC.` | correct |
| 11 | `condition:COTRTUPC.WS-MISC-STORAGE.WS-NON-KEY-FLAGS.WS-EDIT-DESC-FLAGS.FLG-DESCRIPTION-ISVALID` | `corpus/carddemo/app/app-transaction-type-db2/cbl/COTRTUPC.cbl:101` | `88  FLG-DESCRIPTION-ISVALID          VALUE LOW-VALUES.` | correct |
| 12 | `copybook:COSGN00C.CSUSR01Y#1` | `corpus/carddemo/app/cbl/COSGN00C.cbl:55` | `COPY CSUSR01Y.` | correct |
| 13 | `data:COSGN00C.WS-DATE-TIME.WS-TIMESTAMP.FILLER#4` | `corpus/carddemo/app/cpy/CSDAT01Y.cpy:50` | `10  FILLER                    PIC X(01) VALUE ':'.` | correct |
| 14 | `exec-cics:COSGN00C.READ-USER-SEC-FILE#1` | `corpus/carddemo/app/cbl/COSGN00C.cbl:211-219` | `EXEC CICS READ` | correct |
| 15 | `exec-sql:COTRTUPC.9800-DELETE-PROCESSING#1` | `corpus/carddemo/app/app-transaction-type-db2/cbl/COTRTUPC.cbl:1627-1630` | `EXEC SQL` | correct |
| 16 | `file:CBACT01C.OUT-FILE` | `corpus/carddemo/app/cbl/CBACT01C.cbl:35-38` | `SELECT OUT-FILE ASSIGN TO OUTFILE` | correct |
| 17 | `paragraph:COTRTUPC.0000-MAIN-EXIT` | `corpus/carddemo/app/app-transaction-type-db2/cbl/COTRTUPC.cbl:573-575` | `0000-MAIN-EXIT.` | correct |
| 18 | `program:COTRTUPC` | `corpus/carddemo/app/app-transaction-type-db2/cbl/COTRTUPC.cbl:21-1701` | `IDENTIFICATION DIVISION.` | correct |
| 19 | `condition:COTRTUPC.WS-MISC-STORAGE.WS-PFK-FLAG.PFK-VALID` | `corpus/carddemo/app/app-transaction-type-db2/cbl/COTRTUPC.cbl:89` | `88  PFK-VALID                           VALUE '0'.` | correct |
| 20 | `copybook:COTRTUPC.CSSETATY#1` | `corpus/carddemo/app/app-transaction-type-db2/cbl/COTRTUPC.cbl:1358` | `COPY CSSETATY REPLACING` | correct |

## Roadmap items

- [x] **IR models with provenance.** `CobolAdapter` (`src/changeproof/adapters/cobol/`) turns a
  program into entities: program, section, paragraph, data item, 88-level condition, file,
  copybook, call, `EXEC SQL`, `EXEC CICS` and `EXEC DLI` blocks. Every entity carries
  `file:line` or `file:line-end` (`tests/test_cobol_adapter.py`). Ids are built from names,
  never line numbers, so moving code changes nothing, while a changed picture shows up as a
  modified entity at its copybook line (`::test_diff_ignores_moved_lines_and_catches_a_picture_change`).
- [x] **Copybook resolution.** `COPY`, `COPY ... REPLACING` (pseudo-text, words, and IBM
  partial-word tags such as `(TAG)` and `:TAG:`), `REPLACE` / `REPLACE OFF`, and
  `EXEC SQL INCLUDE`. Each inlined line keeps its own file and line. Missing and recursive
  copybooks are reported, not fatal (`tests/test_cobol_preprocess.py`).
- [x] **Crypto-relevant calls tagged as IR entities.** `crypto-call` entities for calls to IBM
  ICSF services (hash, MAC, encrypt, decrypt, key generation and import, random, PIN, signature,
  key agreement), including dynamic calls through a data item's `VALUE`, and for Db2 hash and
  encryption functions inside `EXEC SQL` (`tests/test_cobol_crypto.py`,
  `tests/test_cobol_adapter.py::test_crypto_calls_are_tagged`). Only names are matched; nothing is
  hashed or encrypted (CLAUDE.md rule 6).

## Beyond the exit check

- **All 44 CardDemo programs now produce IR**, up from 40 of 44 that parsed in Week 1. The four
  that failed then used `COPY ... REPLACING`, which the preprocessor now implements. That run
  found 15,846 entities (12,974 data items, 1,162 conditions, 903 paragraphs, 357 copybook
  inclusions, 288 `EXEC` blocks, 64 calls, 54 files, 44 programs). It found no crypto calls,
  which is expected: CardDemo does not use ICSF. The crypto tagging is proven on synthetic code
  only. Output: `docs/weekly/week02-carddemo-ir.json` (`scripts/ir_corpus_run.py`).
- The generated parser is committed (`src/changeproof/adapters/cobol/_generated/`, MIT grammar,
  notice included) and reproducible with `scripts/generate_cobol_parser.sh`. The engine needs no
  JVM. The ANTLR runtime (BSD-3) moved from the spike group to the core dependencies.
- Deep nesting no longer hits Python's recursion limit: parsing runs in a thread with a large
  stack.

## What I changed from the plan, and why

- **No IR cache yet.** ADR 001 planned to cache IR by content hash. A content hash is a hash
  function, and CLAUDE.md rule 6 keeps every hash behind the signer interface, which arrives in
  Week 6. This needs your call (below).
- **ANTLR's fast SLL mode was tried and dropped.** It gives up on ordinary subscripts such as
  `ARR(1)` in this grammar, so it only added time.

## Open issues

- **Speed.** 1,269 CPU seconds for the 44 programs; median 11 s per program, slowest 245 s
  (CORPT00C). Fine for per-change analysis, slow for a first full scan.
- **ICSF and Db2 name tables** were written from memory of IBM's documentation, not checked
  against the ICSF Application Programmer's Guide. They need that check before Week 16 relies on
  them.
- Nested programs and `SECTION`s in real code are untested; CardDemo has neither.
- The NIST suite has not been run through the adapter yet (only through the parser in Week 1).
- The first `FILLER` in a group has no ordinal and later ones do (`FILLER`, `FILLER#2`). Harmless,
  but worth making uniform before ids are stored anywhere.

## Decisions needed from the owner

1. Approve Week 2.
2. IR cache key: wait for the Week 6 signer interface to supply the hash (recommended), or allow
   a non-evidence hash for caching only as a written exception to rule 6.
