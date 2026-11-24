# ADR 015: Boundary round on every path, and joint values for outcomes one field cannot reach

- Status: proposed. The owner chose this as the first remaining MVP piece on 2026-10-24.
- Date: 2026-10-24
- Related: ADR 006 (characterization), ADR 013 (files and packed data), ADR 014 (bank simulation)

## Context

Over 175 simulated days the bank simulation missed 18 changes (`sim/ledger.jsonl` in the project
files, rows with `"outcome": "missed"`). Replaying those 18 commits from the banks' bundles on `main`
gives the same 18 verdicts and the same test counts, so the misses come from the search and not from the
simulation (`scripts/search_replay.py`). There are three causes:

1. **The search stops once every outcome is covered.** In `FEEASSES` the retail waiver threshold is in
   the candidate values, but every retail outcome was reached before any variant set the balance to it
   under segment `R`. The on-point step from ADR 006 can only choose among runs that already happened,
   so the threshold never got a retail test (10 rows: `fee-waiver-strict`, `fee-per-txn-slip`).
2. **A path's only witness can sit on its literal.** After the free-transaction test became `>=`, the
   only test kept for the charging path had exactly the free count, where the per-transaction charge is
   multiplied by zero. A tenfold slip in the charge then changes nothing (part of the 10 rows above).
3. **Some outcomes need several fields set at once.** `POSTTXN`'s overdraft fee runs only when a debit
   exceeds the balance and stays within a non-zero limit. Changing one field at a time from all-zero
   bases never sets the balance, amount and limit together, so `ACCT-BALANCE < 0` was never true and a
   lowered overdraft fee went unseen (6 rows: `post-od-fee-down`).

## Decision

1. **Boundary round.** After the path and on-point choice, every kept run that ran a comparison of an
   input field with a literal is re-run with that field one unit below, on and one unit above the
   literal (`sides` in `adapters/cobol/driver.py`; a text literal has only its on-point). A run is kept if
   it adds a new (field, value, condition) triple. This tests the threshold on the path that compares it,
   and gives each path a witness off the literal.
2. **Joint round.** For each outcome still uncovered after the single-field rounds, the first run that
   reached its decision is the seed. Every input field read by a condition that ran in the seed is reset
   at once: the whole product of their candidate values when it has at most `JOINT_RUNS` (256) members,
   otherwise 256 samples drawn by a `random.Random` seeded with the condition's id and outcome. Runs go in
   builds of 64 and stop once the outcome is reached. Every run joins the results, so path choice and the
   boundary round see them.
3. **Earlier runs are reused.** The search keeps each input set's result, so a boundary input the main
   rounds already ran is scored, not skipped or run twice.
4. **Same bytes from the same source.** The sample's seed comes only from the condition id and outcome,
   and every set is sorted before it becomes input, so the suite stays reproducible (ADR 006 point 7,
   `tests/test_search.py::test_the_wider_search_still_gives_the_same_suite_byte_for_byte`).
5. **A subprogram run whose call failed is now dropped as ADR 006 intended.** The search had shadowed its
   `batch` flag with its list of inputs, so the check never applied to subprograms.

## Consequences

- On the 18 missed simulation commits, 17 are now `not-equivalent` (the 6 overdraft-fee, 6 waiver,
  4 per-transaction and 1 online-limit rows). `intaccr-truncate` is still missed: it needs an input whose
  exact interest sits at a half cent, which is idea 5 in `sim/KNOWLEDGE.md` and stays **planned**.
- The same replay of all 34 recorded refactors keeps them `equivalent` (no false alarm), and all 20
  confirmed intended changes stay `not-equivalent` (`docs/weekly/search-replay.json`). A sample of 40
  caught defects, replayed outside the repository, all stayed caught.
- Suites grow by about 12 tests per bank estate (31-35 to 45-47 across four programs), and the joint
  round can spend up to 256 runs on an outcome no input can reach. Scans take longer accordingly.
- Equivalence is still evidence from tests, not a proof. A condition that compares two fields with no
  literal (idea 4 in `sim/KNOWLEDGE.md`) is reached only if the joint sample happens to land there.
