# ADR 013: COBOL behaviour check on files and packed data

- Status: proposed. Asked for by the owner on 2026-10-19 ("start steps 1 and 2"), as part of making
  COBOL strong for auditors (ROADMAP, MVP lead).
- Date: 2026-10-19
- Related: ADR 006 (characterization), ADR 007 (equivalence)

## Context

The behaviour check (ADR 006) ran only linkage subprograms whose items are plain display text. It
refused `COMP`, `COMP-3`, `OCCURS` and `REDEFINES`, and every program that reads files, Db2 or CICS was
listed untested. Bank code keeps money in packed decimal and does its work in batch jobs on files, so
none of CardDemo was tested.

## Decision

1. **Layouts are rebuilt from the IR.** A generated program declares an area exactly as the program
   does, from the IR entity's own text, so packed and binary numbers, tables and redefinitions keep
   their bytes. Each elementary occurrence is one input or output, keyed by its name and subscript
   (`LK-RATE(2)`). A name declared twice is qualified (`NAME OF RECORD`).
2. **A redefined area is filled through one view:** the first view the program reads, else the base.
   Every view is shown in the output. Pointers, `INDEX`, `COMP-1`, `COMP-2` and `OCCURS DEPENDING ON`
   are still refused with their line.
3. **Batch programs run as themselves, on files built for each test.** The IR now records the modes
   each file is opened in and which FD each record belongs to. A file the program reads gets zero or
   one record, laid out as the program reads it (its `READ ... INTO` area, else the FD record), written
   by a generated loader from the program's own SELECT and FD. After the run a generated unloader
   reads every file the program writes, laid out as it writes them (`WRITE ... FROM`, else the FD
   record), and shows each field of each record as `FILE#n.FIELD`. The program's display output is kept
   as `SYSOUT`, and its return code is part of its behaviour. A batch program with `PROCEDURE DIVISION
   USING` (a JCL `PARM`) is called through the linkage driver with its files in place.
4. **Runs repeat exactly.** Every run gets fresh files in its own folder, the clock is fixed
   (`COB_CURRENT_DATE`, `FIXED_CLOCK`), and stdin is empty. Record counts of 1 and 0 are both tried, so
   the empty-file path is tested.
5. **CICS, Db2 and IMS programs are refused with the line of their first `EXEC` block.** Stand-ins for
   those calls are the next step (**planned**). A program that calls a module outside the corpus
   (an assembler routine or a Language Environment service such as `CEE3ABD`) runs until that call,
   which ends the run with a non-zero return code; that is recorded as behaviour, not hidden.
6. **No schema changed.** Inputs, outputs and return codes go into the existing suite and predicate.

## Consequences

- The search tries boundary values one field at a time, so key matches between files come mainly from
  the low base, where every key is zero. Paths that need two records, or I/O errors, are not reached;
  each condition's coverage is in the suite.
- GnuCOBOL is still not IBM Enterprise COBOL (ADR 006); both sides of a comparison use the same runner.

## Evidence

- `tests/test_cobol_io.py`: packed, binary, table and redefined items become inputs with their usage;
  pointers are still refused with their line; a packed-decimal subprogram is covered down every branch
  and a changed bonus is caught; a batch job runs on generated files, its output files are read back,
  the fixed date shows, and the empty-file path is tested; the same suite comes out byte for byte; a
  changed posting rule is caught; CICS programs are refused with their line; equivalence now tests a
  batch job and a packed subprogram outside the impact set.
- `docs/weekly/cobol-io-carddemo.json` (from `scripts/cobol_io_check.py`): every CardDemo program in
  `app/cbl`, characterized or refused with why, and bugs planted in the posting job `CBTRN02C`.

## CardDemo result (2026-10-19)

`scripts/cobol_io_check.py` on the 31 programs in CardDemo's `app/cbl`. Before this change none could be
tested. Now 11 run: the batch jobs `CBACT01C` to `CBACT04C`, `CBCUS01C`, `CBTRN01C` to `CBTRN03C` and
`CBSTM03B`, plus `COBSWAIT` and `CSUTLDTC`. Two of those (`COBSWAIT`, `CSUTLDTC`) and every record path of
`CBACT01C` stop at a call outside the corpus (an assembler date routine or a Language Environment
service), so their suites hold that stop and little else. 17 are CICS programs, refused with the line
of their first `EXEC CICS`. 3 do not build under GnuCOBOL (`CBEXPORT` and `CBIMPORT` name an item their
copybook does not define here; `CUSTREC.cpy` used by `CBSTM03A` has a picture GnuCOBOL rejects).

The posting job `CBTRN02C` gets 8 tests from 1,658 runs, reaching 58 of its 98 condition outcomes; most of the
rest test a file status other than success (read from the conditions, not traced one by one). All 6 bugs planted in it were caught: the balance update reversed, a credit
and a debit swapped between the cycle totals, the cycle debit added instead of subtracted, the credit limit and expiry
date checks made strict, and the reject return code dropped.

A first run showed differences on every planted bug, inflated by transaction timestamps whose
hundredths of a second came from the real clock; the fixed clock now includes them. A first version
of the second bug (`>= 0` made `> 0`) changes nothing, since adding zero to either cycle total gives
the same result, and the check rightly found no difference; it was replaced by one that swaps the
totals.
