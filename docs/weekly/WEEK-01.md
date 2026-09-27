# Week 1: one build, market rules as profiles

- Market: any software company by default (`general`), with `us-defense` and `eu-dora` as profiles
- Branch: `week-01-universal`, built from the DORA branch `week-01-dora`
- Date: 2026-09-27
- Status: exit check met; ADRs 001 to 004 accepted by the owner on 2026-09-27
- Alternatives: the single-market US (PR #1) and DORA (PR #2) builds were closed unmerged. Their
  reports stay in those PRs and in git history.

## Exit check

| Check | Target | Result | Evidence |
|---|---|---|---|
| Corpus parses | ≥ 90% | **Met with ANTLR4 Cobol85: 481/503 (95.6%)**. Shared with PRs #1 and #2 because the parser does not depend on the market | `spike/results/summary.md`, `docs/adr/001-parser.md` |
| Sample config validates | validates | **Met** for all three markets | `tests/test_config.py::test_roadmap_sample_config_validates`, `::test_each_market_sample_validates` |
| ADRs reviewed | owner review | **Met: accepted 2026-09-27** | `docs/adr/001-parser.md` to `004-market-profiles.md` |

The whole test suite passes: 119 tests with sockets blocked, and again inside a network namespace
with no interfaces.

## What this version adds

- **`market:` setting.** `general` (the default), `us-defense` or `eu-dora`. Each profile sets the
  classification levels, which of them may never send data out, what customer-data egress must
  cite, and the frameworks to map evidence to (`src/changeproof/markets.py`, ADR 004;
  `tests/test_markets.py`).
- **The general profile** uses the classification levels most companies already use and anchors
  on SOC 2 (CC8.1) and ISO/IEC 27001:2022 (Annex A 8.25, 8.28, 8.29, 8.32) change-management
  controls. The mapping itself is **planned** for Week 5.
- **One egress rule set for every market.** `check_egress` takes the profile, and 20 cases cover
  the three markets (`tests/test_egress.py::test_qpu_egress_matrix`). The DORA register and EEA
  rules apply only under `eu-dora` (`::test_region_rule_applies_only_to_dora`).
- **`changeproof init --market <name>`** writes a starter file with that market's default
  classification and frameworks (`tests/test_cli.py::test_init_writes_the_chosen_market`).
- **One `customer` data tier** replaces `customer-unclassified` and `customer-confidential`.
- **Sample configs** for each market in `docs/examples/`.
- **ADRs 002 and 003** now say which parts are market-specific. ADR 004 records the decision.

## Parser check on mainstream languages

A universal market needs languages beyond COBOL. The published tree-sitter grammars parsed real
code with no preprocessing (`spike/mainstream_spike.py`, raw results in
`spike/results/mainstream.json`):

| Language | Sample | Parsed clean | Speed |
|---|---|---|---|
| Java | Apache Commons Lang 3.17.0, 500 files | 100% | about 363,000 lines/s |
| Python | Python 3.12 standard library, 517 files | 100% | about 319,000 lines/s |
| JavaScript | npm 10.9.7, 1,054 files | 99.9% (1 file) | about 270,000 lines/s |

Parsing mainstream languages is the easy part; COBOL was the hard one. Adapters for these
languages (syntax tree to IR with provenance, diff, test runs) are **planned** and not on the
roadmap yet.

## Market direction

Superseded by the owner's decisions below and by the market focus in `ROADMAP.md`: universal
(`general`) is the main path, `eu-dora` the strong second, and `us-defense` stays a tested profile.

## Open issues

- The NIST IR 8547 timeline cited in ADR 004 for the general profile was a draft when last
  checked. It needs rechecking before Week 6.
- One JavaScript file fails to parse (`lib/base-cmd.js:166` in npm). That it is a grammar gap is
  inferred and was not checked further.
- The COBOL parser open issues are unchanged: ANTLR speed, `REPLACING`, and recursion depth.

## Owner decisions (2026-09-27)

1. Week 2 builds on this universal branch. PRs #1 and #2 were closed without merging.
2. Universal (`general`) is the main path and DORA (`eu-dora`) the strong second (final call,
   05:00, after an earlier DORA-first decision). ROADMAP.md and CLAUDE.md say so.
3. ADRs 001 to 004 are accepted.
4. `MyPackages.py`, left over on `main` from before this project, is removed.
