# Week 8: Characterization tests (GnuCOBOL)

- Market: universal build (`general` main path, `eu-dora` strong second, `us-defense` kept passing)
- Branch: `week-08-characterization`, built on `main` after Week 7 (PR #13)
- Date: 2026-10-01
- Status: exit check met

## Why this week matters

Characterization tests record what a program does today, so that Week 9 can rerun them on code a
change did not touch and show its behaviour stayed the same. That is the second half of the engine's
focus: what a change touches, joined with proof that nothing else changed behaviour. The equivalence
attestation itself is still **planned** (Week 9).

## Exit check

| Check | Result | Evidence |
|---|---|---|
| At least one test per extracted condition for 3 batch programs | **Met.** All 21 conditions in `FEECALC` (6), `RISKSCR` (8) and `INTCALC` (7) have tests | `tests/test_characterize.py::test_exit_check_every_extracted_condition_has_a_test` |
| Beyond the check: each condition seen both true and false | **Met** for all 21 | `::test_every_condition_is_seen_both_ways` |
| Golden outputs linked to source | Each condition cites the `file:line` of its `IF`, `WHEN` or `PERFORM UNTIL`, and each test names the conditions it reaches | `::test_golden_outputs_link_to_the_source_lines_they_exercise` |
| Reproducible | A second run gives the same suite byte for byte, and replaying a saved suite gives no differences | `::test_suites_are_reproducible`, `::test_committed_golden_suites_still_hold` |

The three programs are synthetic linkage subprograms written for this week
(`corpus/synthetic/batch/`): an account fee, a credit risk grade with a loop, and deposit interest.

| Program | Conditions | Seen both ways | Tests (one per path) | Runs tried |
|---|---|---|---|---|
| FEECALC | 6 | 6 | 11 | 156 |
| RISKSCR | 8 | 8 | 21 | 493 |
| INTCALC | 7 | 7 | 13 | 144 |

The golden suites are in `docs/weekly/week08-golden/`. Each holds the source's SHA-384 digest, the
runner (`cobc (GnuCOBOL) 3.1.2.0`), the boundary values tried for each linkage item, every
condition with its line, and every test with its inputs, outputs and output digest.

## Roadmap items

- [x] **Offline Dockerized GnuCOBOL.** `docker/gnucobol/Dockerfile` pins `gnucobol3=3.1.2-5.1ubuntu1`
  on Ubuntu 24.04. `changeproof characterize --docker <image>` runs with `--network none` and mounts
  only a work folder holding a copy of the source (`::test_the_docker_runner_has_no_network_and_sees_only_its_work_folder`).
  The same script runs locally with `cobc`. CI installs the same package version, builds the image
  and replays the three golden suites inside it. The image could not be built in this session
  (Docker Hub answered 429 Too Many Requests), so the container replay is proven by CI only.
  Characterization makes no network call (`tests/test_offline.py::test_characterization_makes_no_network_calls`).
- [x] **Boundary inputs.** Each linkage item the program reads gets zero, its largest value, every
  numeric literal in the program one unit either side, its 88-level values and the strings its
  conditions compare it with (`::test_boundary_candidates_sit_on_and_either_side_of_each_literal`).
  The search changes one item at a time from low, middle and high starting points, then again from
  every run that reached a new outcome.
- [x] **Golden outputs linked to source.** The adapter now records each decision as a `branch`
  entity with its condition and the lines each outcome runs (`tests/test_cobol_branches.py`).
  GnuCOBOL's `-ftraceall` trace shows which lines ran, so outcomes are read, not guessed
  (`::test_outcomes_read_each_kind_of_branch_from_line_counts`). `CobolAdapter.run` now returns a
  real observation instead of raising (`::test_a_run_through_the_adapter_returns_the_golden_output`).
- **Early look at Week 9.** `changeproof characterize --replay <suite>` reruns a saved suite on
  today's source and lists every output that differs. Changing `FEECALC`'s personal fee rate from
  0.015 to 0.016 is caught, and only `LK-FEE` differs (`::test_replay_catches_a_changed_behaviour`).
  Signing and the mutation check are Week 9.

ADR 006 records the design. The whole suite passes with sockets blocked: 354 tests.

## Outside facts (project rule 6)

| Reference | Status |
|---|---|
| GnuCOBOL 3.1.2 licenses (compiler GPL-3.0-or-later, `libcob` LGPL-3.0-or-later) | read from the installed package's Debian copyright file on 2026-10-01 |
| Ubuntu 24.04 package `gnucobol3` version `3.1.2-5.1ubuntu1` | read from `apt-cache policy` on an Ubuntu 24.04 machine on 2026-10-01 |
| `-ftraceall`, `COB_SET_TRACE` and `COB_TRACE_FILE` behaviour | observed by running GnuCOBOL 3.1.2; the trace format is checked by the tests above |

## Open issues

- **GnuCOBOL is not IBM Enterprise COBOL.** Truncation, size errors and collating can differ, so
  golden outputs describe behaviour under GnuCOBOL. Week 9 compares a program with its own earlier
  version under the same runner.
- **Only linkage subprograms with display items.** `COMP`, `COMP-3`, `OCCURS` and `REDEFINES`
  linkage items are refused with their line. Programs that read files, Db2 or CICS need stubs:
  **planned**.
- **CardDemo is not characterized yet.** Its programs are CICS or file-driven, so they wait on stubs.
- **The container image was not built here** (Docker Hub rate limit). CI builds and uses it.

## Decisions needed from the owner

None to merge. ADR 006 (characterization) is proposed and goes in with this week, as the workflow
allows.
