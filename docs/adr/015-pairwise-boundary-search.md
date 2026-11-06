# ADR 015: Search two inputs together around each boundary

- Status: proposed. Asked for by the owner on 2026-11-06 ("Start both and run a test now and log the
  simulation"), in reply to the proposal to fix the engine's top gap from the bank simulation.
- Date: 2026-11-06
- Related: ADR 006 (characterization), ADR 007 (equivalence), ADR 014 (bank simulation)

## Context

The bank simulation (ADR 014) missed 18 of its first 3894 scans. The cause of most of them was the
characterization search (`src/changeproof/characterize/__init__.py`, `search`):

- It changes one input at a time from three bases and stops when every condition has been seen both
  ways. The overdraft fee in `POSTTXN` only runs for a debit larger than the balance but within a
  non-zero limit, so it needs the balance, the amount and the limit set together. The fee line was never
  run, so a changed fee was never seen (`post-od-fee-down`, 6 misses).
- Branch coverage was met before the retail fee waiver in `FEEASSES` was ever run with the balance on its
  minimum. The minimum was in the candidate pool but only tried with a business or student segment
  (`fee-waiver-strict`, 6 misses).
- Once a bank made its free-transaction test inclusive (`>=`), the kept test sat on the threshold, where
  the per-transaction charge is multiplied by zero (`fee-per-txn-slip`, 4 misses).

## Decision

1. **A second, targeted round after the one-field search.** For each condition that still lacks an
   outcome, or a value on or one unit either side of a literal it compares (the value must be in the
   field's candidate pool), take up to `PAIR_SEEDS` runs that reached it, one per path. Vary them one
   boundary field at a time; if the condition is still open, vary every pair of boundary fields over
   their candidate values (`pairs`). Boundary fields are the ones a condition compares with a literal.
   The round stops for a condition as soon as nothing is open, and spends at most `PAIR_BUDGET` runs per
   program.
2. **Keep a test next to each boundary, not only on it.** Besides the first run down each path, the
   suite keeps the first run that holds each on-point value or a neighbour one unit either side
   (`around`), while the condition comparing it ran. A run one step past an inclusive threshold is then
   kept, so arithmetic on that path is not multiplied by zero.
3. **The search no longer reuses its batch flag's name for the input list.** That reuse made the
   "skip a subprogram run whose call failed" rule dead code; it now applies as written.

## Evidence

- `tests/test_pairwise.py` builds a simulated bank's own programs and shows each missed change is now
  seen by replay: the overdraft fee path is covered both ways and a lowered fee differs, the retail
  waiver gets a segment `R` test on its minimum and the strict test differs, and a test one past an
  inclusive threshold is kept and the slipped rate differs. Three refactors still replay clean.
- Re-scan of the saved simulation (`scripts/bank_sim_rescan.py`, results logged in the simulation's
  `KNOWLEDGE.md`, 2026-11-06): 17 of the 18 missed rows are now caught or confirmed, all 34 refactors
  still proven, all 20 confirmed intended changes still confirmed, and the first caught row of each defect
  at each bank (48 rows) still caught.

## Consequences

- Suites are larger (about 43 to 45 tests per four-program scan in the re-scan, against 31 to 35 in the
  ledger) and characterization costs more runs (Prairie Ledger's `POSTTXN`: 687 runs against 279).
- The one remaining miss, `intaccr-truncate` (rounding mode), is not a boundary problem. It needs a run
  whose exact result sits at a half cent or above, which is **planned** (simulation idea 5).
- A condition that can never reach an outcome (dead code) costs up to `PAIR_BUDGET` runs every time the
  program is characterized.
