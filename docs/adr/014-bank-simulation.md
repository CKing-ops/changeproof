# ADR 014: Six synthetic banks and a scan that runs while the owner is offline

- Status: proposed. Asked for by the owner on 2026-10-19 ("generate synthetic ... data for 3 banks ...
  Lets make 3 in U.S, 3 in EU ... start having agents running while I am offline to build the agents
  knowledge for our product and how we can better strengthen our engines capabilities for partnerships").
- Date: 2026-10-19
- Related: ADR 004 (market profiles), ADR 007 (equivalence), ADR 013 (files and packed data)

## Context

The engine is tested on fixtures and on public corpora, one change at a time. A bank sees it differently:
a steady stream of changes, most harmless, some wrong, made by people who sometimes skip the approval
step. We need to know how the engine does on that stream, where it misses, and what to fix first before
a design partner sees it. No real bank code may be used (CLAUDE.md compliance guardrails).

## Decision

1. **Six invented banks.** Three in the US on the `general` profile and three in the EU on `eu-dora`
   (`src/changeproof/banksim/banks.py`). Names, people and numbers are made up and stand for no real
   institution. Every bank runs the same four COBOL programs, so results compare across banks; only the
   business rules differ (rate tiers, day count 365 or 360, fees, limits, overdraft fee):
   interest accrual `INTACCR`, monthly fee `FEEASSES`, payment screening `PAYSCRN` (linkage subprograms,
   packed decimal) and the nightly posting job `POSTTXN` (files, return code).
2. **A catalogue of changes with known truth.** Twenty changes per bank (`estate.py`): refactors that keep
   behaviour (including one that only looks risky, `>` to `>=` where the extra case adds zero), defects
   that break it while their commit message calls them a tidy-up, and intended rule changes. Each is
   committed under one of four approval paths: governed, self-approved, no ticket, or emergency.
3. **One simulated business day** (`run.py`): each bank commits one change; the engine builds the
   change record and runs behavioural equivalence over every program (`--scope full-suite`). The result
   is scored against the truth: `proven`, `caught`, `confirmed`, `missed`, `false-alarm` or
   `inconclusive`, and for approvals `flagged`, `clean`, `missed` or `false-flag`. Main keeps the change
   only when its reviewers would accept it on that evidence; a missed defect is kept, as it would be at a
   bank. Every row carries the commit and the `file:line` of the change.
4. **It carries on between runs.** The ledger, scorecard and each bank's history (a git bundle) are
   saved to a keeping folder after every day, so a fresh machine continues the stream.
   `scripts/bank_sim.py` runs N days. A scheduled task runs it while the owner is offline and writes
   what it learns to a notes file next to the ledger. Those notes are commentary on the scores, not
   evidence; the scores come only from the engine and the catalogue (CLAUDE.md rule 3).
5. **No schema changed and nothing leaves the machine.** The simulation calls the engine's existing
   functions offline.

## Consequences

- The catalogue is the limit: the engine is scored only on changes someone thought to write down.
  Growing it (copybook changes, multi-program changes, CICS once stand-ins exist) is how the simulation
  gets harder.
- A miss is a lead, not a verdict: it may be a search gap in characterization or a change whose effect
  the generated inputs cannot reach.

## Evidence

- `tests/test_banksim.py`: three US banks on `general` and three EU banks on `eu-dora`; every estate
  parses and every catalogued change applies once; a planted rounding defect is caught and kept off main;
  a refactor is proven equivalent and merged; approvals are scored from the change record; the ledger and
  scorecard add up and the stream repeats; a saved simulation carries on from its bundles.

## First run (2026-10-19)

Two simulated days across all six banks (12 changes, 328 seconds of scanning): 6 refactors proven
equivalent, 2 defects caught (a 365 to 360 day count, a dropped reject return code), 2 intended changes
confirmed, both approval gaps flagged, no false alarms. Two changes were **missed**: a retail fee waiver
test made strict at Copperline (`src/FEEASSES.cbl:24`, the balance exactly at the minimum was never
tried) and a lower overdraft fee at Banca Serravento (`src/POSTTXN.cbl:94`, no generated test posts a
debit that takes the balance below zero within its limit). Both are characterization search gaps and
the first things the simulation says to strengthen.
