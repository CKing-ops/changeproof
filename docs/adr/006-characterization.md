# ADR 006: Characterization tests for COBOL

- Status: proposed (Week 8). The owner's workflow merges each week once its exit check passes, so
  this stands until the owner says otherwise.
- Date: 2026-10-01
- Related: ROADMAP.md Weeks 8-9, ADR 003 (egress)

## Context

Week 8 needs characterization tests for COBOL batch programs: boundary inputs, golden outputs linked
to source, and at least one test per extracted condition. Week 9 replays those tests on code outside
a change's impact set to show its behaviour did not change. Analysis stays offline (rule 4), and the
tests must come from parsers and runs, never from an LLM (rule 3).

## Decision

1. **Decisions are IR facts.** The adapter records every `IF`, each `EVALUATE ... WHEN` and every
   `PERFORM ... UNTIL` as a `branch` entity with its condition text, the names it reads, the first
   line each outcome runs, and `file:line` provenance. The program entity records its
   `PROCEDURE DIVISION USING` list in call order. No core schema changed (rule 8).
2. **Linkage subprograms run through a generated driver.** The driver declares the program's
   linkage items in its own working storage, reads one value per elementary item from stdin
   (numbers through `FUNCTION NUMVAL`), calls the program and displays every item. Items the driver
   cannot fill as text (`COMP`, `COMP-3`, `BINARY`, `OCCURS`, `REDEFINES`, pointers) are refused with
   their line, not guessed.
3. **Outcomes come from GnuCOBOL's own trace.** The program under test is compiled with
   `-ftraceall`; each run's trace gives how often each line ran. A branch went true when its true
   line ran, and false when its false line ran or, without an else, when the decision ran more often
   than its true line. A `PERFORM UNTIL` that finished met its condition. Nothing is instrumented by
   hand.
4. **Inputs are boundary values from the program.** For each item the program reads: zero, the
   largest value its picture holds, each numeric literal in the program one unit either side, its
   88-level values and the strings its conditions compare it with. The search starts from low, middle
   and high bases, changes one item at a time, and repeats from every run that reached a new outcome.
5. **One test per path.** The suite keeps the first run down each distinct set of outcomes. That is
   more than a minimal branch cover. While building Week 8, a minimal cover of `FEECALC` missed a
   changed personal fee rate, because its only personal run was raised to the minimum fee. The path
   suite catches that change (`tests/test_characterize.py::test_replay_catches_a_changed_behaviour`).
6. **The same script runs locally and in a container.** `docker/gnucobol/Dockerfile` pins
   `gnucobol3=3.1.2-5.1ubuntu1` on Ubuntu 24.04. Runs use `--network none` and see only a work
   folder with a copy of the source. Local runs use `cobc` from `PATH` or `$CHANGEPROOF_COBC`. CI
   installs the same package version, runs the tests, and replays the committed golden suites
   inside the container.
7. **Suites are plain JSON and reproducible.** A suite holds the source digest (SHA-384, through the
   signer interface), the runner, the boundary values tried, each condition with its provenance and
   the tests that reach it, and each test's inputs, outputs and output digest. It has no timestamp,
   so the same source and runner give the same bytes.

## Consequences

- GnuCOBOL (GPL-3.0 compiler, LGPL-3.0 runtime) must be installed or available as the image. It is a
  tool, like git and OPA: nothing of it is copied or shipped (`docs/licenses.md`).
- GnuCOBOL is not IBM Enterprise COBOL. Numeric truncation, `SIZE ERROR` and collating rules can
  differ, so golden outputs describe behaviour under GnuCOBOL. Week 9 compares a program with its
  own earlier version under the same runner, which this difference does not affect.
- Only linkage subprograms with display items are covered. Programs that read files, Db2 or CICS
  need stubs, which are **planned**.
- Signing suites and the equivalence attestation are Week 9.
