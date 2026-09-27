# Week 1 (DORA market): repo, universal schemas, crypto-agility ADR, parser

- Market: EU financial sector under DORA (ROADMAP.md "Secondary", and the Week 0 fallback).
  Target customer: EU banks and payment firms that run COBOL.
- Branch: `week-01-dora`, built from the finished US Week 1 branch `week-01-foundations`
- Date: 2026-09-27
- Status: exit check run; parse rate met; ADRs waiting for owner review

## Exit check

| Check | Target | Result | Evidence |
|---|---|---|---|
| Corpus parses | ≥ 90% | **Met with ANTLR4 Cobol85: 481/503 (95.6%)**. This result is shared with the US branch because the parser does not depend on the market | `spike/results/summary.md`, `docs/adr/001-parser.md` |
| Sample config validates | validates | **Met** with the DORA sample (`eu-payments-core`) | `tests/test_config.py::test_roadmap_sample_config_validates`, `::test_sample_config_validates_against_json_schema` |
| ADRs reviewed | owner review | **Waiting on owner** | `docs/adr/001-parser.md`, `002-crypto-agility.md`, `003-data-egress.md` |

The whole test suite passes: 82 tests with sockets blocked, and again inside a network namespace
with no interfaces.

## What was reused as-is

Nothing in these parts depends on the market, so they are identical to `week-01-foundations`:
the repo scaffold, CI, the zero-network tests, the adapter interface, the provenance model,
`changeproof init`/`validate`/`schema`, the impact and behavioral-equivalence predicates, the
corpus, and the parser spike with ADR 001.

## What changed for DORA

| US anchor | DORA / EU replacement | Where |
|---|---|---|
| `classification: unclassified \| cui` | Bank-style `public \| internal \| confidential \| restricted`; default `internal` | `src/changeproof/config.py` |
| Data tier `customer-unclassified` | `customer-confidential` | `config.py`, `egress.py` |
| CUI and classified: never leave | `restricted` systems (personal data, payment credentials, supervisory information): never leave | `egress.py`, ADR 003 |
| Customer egress needs approval + approved vendor | Also needs `ict_register_ref` (the vendor's entry in the DORA Art. 28(3) register of information) and `processing_region` of `eea` or `adequacy` (DORA Art. 30, GDPR Chapter V) | `config.py`, `egress.py`, ADR 003 |
| `cnsa2` profile forces PQ transport | `hybrid` and `nist-pqc` profiles force PQ transport; default profile `hybrid` | `egress.py`, ADR 002 |
| CNSA 2.0 deadlines | RTS 2024/1774 Art. 6(4) (update crypto as cryptanalysis develops; Recital 9 names quantum threats) and the EU PQC roadmap of 23 June 2025 (start by end of 2026, high-risk systems by end of 2030, as far as feasible by 2035) | ADR 002 |
| `crypto-inventory` finding field `cnsa2_category` | `migration_category` + `migration_deadline` | `crypto-inventory-v0.1.json` |
| FIPS 140-3 validated modules | Common Criteria or national certification, as well as or instead of FIPS | ADR 002 |
| Frameworks `nist-ssdf, nist-800-53-*, swft, cnsa2` | `dora, dora-rts-ict-risk, eu-pqc-roadmap, gdpr` in the sample config | `docs/examples/changeproof.yaml` |
| Corpus rule: no CUI or classified code | No bank code, customer data or personal data | `CLAUDE.md` |

New tests cover every tier and region combination for the DORA egress rules
(`tests/test_egress.py::test_qpu_egress_matrix`, 10 cases) and reject US-only values
(`tests/test_config.py::test_us_only_values_are_rejected`).

## What did not change

Plans after Week 1 are the same as in ROADMAP.md. Week 5's framework mapping is still the place
where DORA RTS Art. 17 (ICT change management) gets mapped in full. Week 2 has not started for
either market.

## Open issues

- The EU dates and agency guidance in ADR 002 were checked against published summaries in
  September 2026, not the primary texts. BSI and ANSSI's preference for hybrid schemes especially
  needs rechecking before Week 6.
- The config records approval and register references, but cannot check them against a bank's
  real register of information. The Week 20 egress attestation carries them for auditors.
- The same parser open issues as the US branch: ANTLR speed, `REPLACING`, and recursion depth.

## Decisions needed from the owner

1. Choose the lead market: US (`week-01-foundations`, PR #1) or DORA (this branch).
2. Review and approve ADRs 001, 002 and 003 for the market you pick.
