# ADR 001: COBOL parser

- Status: accepted by the owner on 2026-09-27 (Week 1)
- Date: 2026-09-27
- Related: ROADMAP.md Weeks 1-2, `spike/`, `docs/licenses.md`

## Context

The COBOL adapter (Week 2) needs a parser that runs offline in Python 3.12, carries line numbers
through to every IR fact, has a permissive license, and does not put a JVM into the air-gapped
bundle. The owner chose a Python-only spike between two candidates:

- **tree-sitter-cobol** (yutaro-sakamoto, MIT) through py-tree-sitter (MIT). C parser, loaded
  from a compiled shared library.
- **ANTLR4 Cobol85 grammar** (grammars-v4, MIT, from the ProLeap project) with the ANTLR Python
  runtime (BSD-3). Java is used once, at build time, to generate the Python parser.

## Method

`spike/build.sh` builds both from pinned commits. `spike/parser_spike.py` parses every program in
the corpus with both and counts a program as parsed only when the parser reports **zero** syntax
errors. Both candidates receive identical input from a shared preprocessor the spike had to write,
because neither parser handles these on its own:

1. **Copybooks inlined** after their `COPY` statement (no `REPLACING` yet), then the `COPY`
   statement blanked.
2. **`EXEC SQL|CICS|DLI ... END-EXEC` blanked**, leaving `CONTINUE` in the procedure division.
3. **Separator commas and semicolons** turned into spaces outside literals.
4. For ANTLR only, fixed-format columns converted to free form and comment entries (`AUTHOR.` etc.)
   tagged the way its grammar expects. Both conversions keep every line on its original line number.

The NIST CCVS85 suite is not valid COBOL until its placeholders are expanded, so
`scripts/fetch_corpus.py` applies the suite's documented default expansion: optional-feature lines
(a letter in column 7) become comments, and `XXXXXnnn` placeholders get implementor values of the
right syntactic kind.

Corpus: 503 programs, 375,315 source lines. 44 are AWS CardDemo programs (CICS, DB2, IMS, MQ) and
459 are NIST CCVS85 programs. The run used 4 worker processes with a 300 s per-file limit.

## Results

Raw per-file results: `spike/results/per_file.jsonl`. Summary: `spike/results/summary.md`.
Reproduce with `bash spike/build.sh && uv run python scripts/fetch_corpus.py && uv run --group spike python spike/parser_spike.py`.

| Corpus | Candidate | Files | Parsed clean | Rate | Median s/file | Max s/file | Total CPU s |
|---|---|---|---|---|---|---|---|
| CardDemo | tree-sitter-cobol | 44 | 32 | 72.7% | 0.008 | 0.063 | 0.5 |
| CardDemo | antlr4-cobol85 | 44 | 40 | 90.9% | 10.7 | 201.2 | 1,077 |
| NIST | tree-sitter-cobol | 459 | 410 | 89.3% | 0.008 | 0.041 | 4.5 |
| NIST | antlr4-cobol85 | 459 | 441 | 96.1% | 4.5 | 43.3 | 2,650 |
| **All** | **tree-sitter-cobol** | **503** | **442** | **87.9%** | | | **5.0** |
| **All** | **antlr4-cobol85** | **503** | **481** | **95.6%** | | | **3,727** |

What failed:

- **Both parsers (17 programs):** the NIST `SM` module, which tests `COPY ... REPLACING` and
  `REPLACE` semantics the spike's inliner does not implement; CardDemo programs that use
  `COPY ... REPLACING` (COACTUPC, COTRTUPC, COTRTLIC); and four NIST programs with edge-case
  syntax (NC174A, NC205A, NC254A, NC401M). Most of these are preprocessor gaps, not grammar gaps.
- **tree-sitter only (44):** grammar gaps. Examples: `NOT=` with no space, an empty
  `DATE-COMPILED.` paragraph, `PROGRAM-ID. X IS INITIAL`, the IBM `ENTRY` statement, a continued
  literal containing quotes, and the optional COBOL-85 modules for communication (`CM`), debugging
  (`DB`) and report writer (`RW`).
- **ANTLR only (5):** two `RecursionError`s on deeply nested conditions (NC207A, NC246A), one
  timeout over 300 s (NC210A), COPAUS2C and OBNC1M.

## Decision

**Use the ANTLR4 Cobol85 grammar with the Python target**, behind the adapter interface, fed by a
changeproof-owned preprocessor.

- It is the only candidate that clears the Week 1 exit check (95.6% against the 90% target) and
  clears it on the real-world corpus too (CardDemo 90.9%).
- Its grammar comes from ProLeap, which has been used on production COBOL, and covers COBOL-85
  including the optional modules.
- Java is a build-time tool only. The generated Python parser is committed (Week 2), so neither
  the runtime nor the air-gapped bundle needs a JVM.

The preprocessor becomes Week 2 adapter code, not throwaway spike code. It must add `REPLACING` and
`REPLACE` and keep a line map, so every fact from an inlined copybook points to the copybook's own
`file:line`.

## Consequences

- **Speed is the cost.** The Python ANTLR runtime is about 750 times slower than tree-sitter here
  in total run time over the corpus (the median per-file ratio is about 530 times): about 100
  lines per CPU-second, against more than 75,000. A full first parse of a 20-million-line
  estate would take about 55 CPU hours. Per-change analysis only reparses changed files and their
  dependents, so Week 2 will cache IR by content hash. If that is still too slow, the same grammar
  can be generated for ANTLR's C++ target (BSD-3) and loaded from Python. One wrapper for that,
  speedy-antlr-tool, declares both BSD-3 and GPLv3 in its PyPI metadata; do not adopt it until its
  license is confirmed.
- **Deep nesting** hits Python's recursion limit on two programs. Week 2 either raises the limit in
  a worker thread with a larger stack or rewrites the affected rules.
- **tree-sitter stays a fallback.** If the speed cost proves unacceptable, a forked
  tree-sitter-cobol with the grammar fixes listed above is the alternative. Its gaps are specific
  and fixable, but none of them is fixed yet.
- The generated parser is about 2 MB of Python. It is generated from an MIT grammar and is
  committed with the grammar's license notice.

## Alternatives considered

- **ProLeap (Java).** The most mature option, but it puts a JVM into the offline bundle. The owner
  ruled it out before the spike.
- **GnuCOBOL `cobc -fsyntax-only`.** Useful as an oracle, but it is GPL, needs a native install, and
  exposes no syntax tree.
