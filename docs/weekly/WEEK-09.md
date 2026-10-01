# Week 9: Behavioral-equivalence attestation

- Market: universal build (`general` main path, `eu-dora` strong second, `us-defense` kept passing)
- Branch: `week-09-equivalence`, built on `main` after Week 8 (PR #14)
- Date: 2026-10-01
- Status: exit check met (95%), after one change to how suites are chosen; see below

## Why this week matters

This is the second half of the engine's focus: proof that nothing outside a change altered its
behaviour, next to what the change touches. For COBOL linkage subprograms, the two halves now exist
as two signed predicates. The equivalence predicate names the impact statement by its digest, and
the policy gate checks both. A single combined record per change is still **planned**.

## Exit check

| Check | Result | Evidence |
|---|---|---|
| 20-bug mutation check: at least 85% caught | **Met: 19 of 20 (95%)** | `tests/test_equivalence.py::test_exit_check_the_tests_catch_at_least_85_percent_of_seeded_bugs`; end to end through git and `equivalence --scope full-suite` in `scripts/mutation_check.py` (`docs/weekly/week09-mutation.json`) |
| Kill gate: under 60% | Not triggered | as above |
| Each seeded bug is a real behaviour change | All 20 change the outputs on a stated witness input | `::test_every_seeded_bug_changes_behaviour_on_its_witness` |

### How the number moved, in order

1. The 20 bugs (`tests/fixtures/equivalence/bugs.py`) were written before the check first ran, one
   per common mistake. The first run, with Week 8's one-test-per-path suites, caught **16 of 20
   (80%)**. That is under the 85% target and over the 60% kill gate. All four misses moved a
   comparison by one (`<=` to `<`, `>` to `>=`), and no kept test sat exactly on those values.
2. Before changing anything, ten more bugs were written as a held-out set (`HELD_OUT` in the same
   file). The path-only suites caught **8 of 10**.
3. The suites now also keep the first run that puts each input exactly on a literal it is compared
   with, counted only when that comparison ran. This is standard on-point boundary testing, and
   Week 8 had promised boundary inputs. The 20 bugs: **19 of 20 (95%)**. The held-out bugs: still
   **8 of 10** (`::test_held_out_bugs_written_before_the_boundary_runs_were_added`).

The 95% was reached after seeing which bugs were missed, so the held-out 80% is the fairer view of
what the method does on new bugs. Over all 30 bugs, 27 are caught (90%). The three misses (R2, H3,
H6) all compare a computed field on its boundary (`WS-UTIL >= 90`, `LK-FEE < 2.50` after the
COMPUTE, `WS-SCORE >= 70`). Inputs alone do not land those fields exactly on the literal; that needs
values from inside the run, which is **planned**.

R2 matters beyond the score. On that commit the verdict was `equivalent` although the program's
behaviour had changed for one exact input. An `equivalent` verdict means "no test showed a
difference", and the attestation carries the test count with it. It is not a proof over all inputs.

## Roadmap items

- [x] **`changeproof equivalence` runs tests outside the impact set.** Each program is characterized
  at the base of the change (ADR 006) and replayed at the head. By default only programs that own
  no changed or impacted entity are tested.
  - A refactor of FEECALC leaves RISKSCR and INTCALC equivalent
    (`::test_a_refactor_leaves_everything_outside_the_impact_set_equivalent`).
  - An intended rate change is inside the impact set, so it does not count against the change.
    With `--scope full-suite`, the same change is `not-equivalent` and only FEECALC differs
    (`::test_an_intended_change_is_inside_the_impact_set_and_does_not_count_against_it`).
  - The refactor gives no false alarm, even on FEECALC
    (`::test_a_refactor_is_equivalent_even_on_the_program_it_changed`).
  - A program that cannot be tested (here a `COMP-3` linkage item) is listed with its line and
    reason, and the verdict becomes `inconclusive`
    (`::test_programs_that_cannot_be_characterized_make_the_verdict_inconclusive`).
  - Baselines are kept by source digest and reused
    (`::test_baselines_are_kept_by_source_digest_and_reused`).
- [x] **Signed attestation.** `changeproof equivalence --key` signs the predicate as an in-toto
  statement about the head commit, through the signer interface. It verifies offline
  (`::test_cli_signs_the_attestation`). The predicate carries the impact statement's SHA-384 digest
  (`::test_the_attestation_names_the_impact_statement_it_excludes`).
- [x] **20-bug mutation check.** See the exit check above.
- **Policy gate.** `equivalence-required-outside-impact-set` is now a Rego rule, no longer
  not-evaluated. It denies a test that differs outside the impact set (Rego unit tests in
  `tests/policies/`) and warns for each program it cannot test. On the Week 7 billing platform, six
  programs have no `USING` and TAXCALC does not build without its copybook folder, which the gate
  test does not pass. The rule is reported `inconclusive` with seven warnings: it does not fail the
  gate, and OSCAL records it as not satisfied with the reason, never as satisfied
  (`tests/test_gate.py::test_the_equivalence_rule_warns_about_each_program_it_cannot_test`).
  Without GnuCOBOL the rule is not-evaluated, never passed
  (`::test_without_gnucobol_the_equivalence_rule_is_not_evaluated`).

The draft `behavioral-equivalence` v0.1 predicate gained one optional field, `untested`. No other
schema changed. ADR 007 records the design. The framework mapping now cites the equivalence test
for SOC 2 CC8.1, ISO A.8.29, RTS Art. 17(1)(a) and the other rows that listed it; those control
numbers stay **unverified** as before.

The whole suite passes with sockets blocked: 366 tests.

## Outside facts (project rule 6)

None new this week.

## Open issues

- **Computed-field boundaries** are missed (three of 30 bugs). Values from inside the run are
  **planned**.
- **Only linkage subprograms** can be tested. Batch programs that read files, and Db2 or CICS
  programs, show as untested until stubs exist (**planned**). That includes all of CardDemo and the
  Week 5 billing platform.
- **One combined record per change** (impact and equivalence in one predicate) is **planned**. Today
  they are two predicates, linked by digest.
- **The held-out set is small** (10 bugs) and written by the same author as the method. An
  independent bug set, ideally seeded by someone else, would be a stronger check.

## Decisions needed from the owner

None to merge. ADR 007 is proposed and goes in with this week, as the workflow allows.
