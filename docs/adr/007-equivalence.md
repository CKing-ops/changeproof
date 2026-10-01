# ADR 007: Behavioral-equivalence evidence

- Status: proposed (Week 9). The owner's workflow merges each week once its exit check passes, so
  this stands until the owner says otherwise.
- Date: 2026-10-01
- Related: ROADMAP.md Week 9, ADR 005 (policy gate), ADR 006 (characterization)

## Context

The engine's focus is the link between what a change touches and proof that nothing else changed
behaviour. Week 5 built the first half (impact). Week 9 builds the second: run tests outside the
impact set, sign the result, and show with a 20-bug mutation check that the tests catch real bugs
(at least 85%, with a kill gate under 60%).

## Decision

1. **Baselines come from the base of the change.** For each COBOL program, a characterization
   suite (ADR 006) is built from the program as it was before the change, then replayed on the same
   program at the head. Nothing is compared against hand-written expectations. `--baselines <dir>`
   keeps suites by source digest and runner, so an unchanged program is characterized once.
2. **Scope follows the impact predicate.** By default only programs outside the impact set are
   tested: programs that own no changed or impacted entity. The predicate records the SHA-384
   digest of the impact statement it used, so the two pieces of evidence are joined by digest.
   `--scope full-suite` tests every program, including the ones the change was meant to alter.
3. **Gaps are evidence too.** A program in scope that cannot be tested (no `USING`, a `COMP-3`
   linkage item, no base version, a build failure) is listed in `untested` with its line and the
   reason. Any entry makes the verdict `inconclusive`, never `equivalent`. `untested` is a new
   optional field in the draft `behavioral-equivalence` v0.1 predicate. Nothing else in the schema
   changed.
4. **The verdict is mechanical.** `not-equivalent` if any test's output or exit code differs.
   `inconclusive` if a test errored, a program is untested, or nothing was tested. `equivalent`
   otherwise.
5. **Signing goes through the signer interface.** `changeproof equivalence --key` wraps the
   predicate in an in-toto statement about the repository at the head commit and signs it, as
   `impact --key` does (ADR 002).
6. **The gate rule uses the same run.** `equivalence-required-outside-impact-set` is now a Rego rule.
   It denies a test that differs outside the impact set and warns for untested programs and errors.
   When the verdict is inconclusive, the rule is `inconclusive`: it does not fail the gate, and its
   OSCAL finding is not satisfied, with the reason in its remarks.
   If GnuCOBOL is missing, the rule is `not-evaluated` with the reason, never passed (ADR 005).
7. **Suites also keep on-point boundary runs.** The first mutation run caught 16 of 20 bugs; all four
   misses were comparisons moved by one (`<=` to `<`, `>` to `>=`). A path-only suite kept no run
   sitting exactly on those literals. Suites now also keep the first run that puts each input field
   exactly on a literal it is compared with, counted only when that comparison ran. Ten more bugs
   were written after the first run and before this change, as a held-out set. Their score is
   reported beside the main one.

## Consequences

- The proof covers COBOL linkage subprograms. Programs that read files, Db2 or CICS show as
  untested until stubs exist (**planned**).
- A boundary that compares a computed field (for example `WS-SCORE >= 40` after several `ADD`s) is
  not found by input-side boundary values. Two of the ten held-out bugs and one of the twenty are
  of that kind. Reaching them needs values from inside the run, which is **planned**.
- Behaviour is compared under GnuCOBOL, before and after, on the same runner (ADR 006).
