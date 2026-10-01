# Week 7: OSCAL output and policy gate

- Market: universal build (`general` main path, `eu-dora` strong second, `us-defense` kept passing)
- Branch: `week-07-oscal-policy`, built on `main` after Week 6 (PR #12)
- Date: 2026-10-01
- Status: exit check met

## Why this week matters

The gate turns impact evidence into a decision on each change, and the OSCAL output hands that
decision to an assessor's tools. The equivalence half of the engine's claim is still **planned**
(Weeks 8-9). Until it exists, the gate reports that rule as not evaluated rather than passing it.

## Exit check

| Check | Result | Evidence |
|---|---|---|
| OSCAL validates | **Met.** Every gate run on the seeded repository produces assessment results that validate against NIST's OSCAL 1.1.2 schema. So does NIST's own example, and removing a required field fails | `tests/test_gate.py::test_exit_check_oscal_assessment_results_validate`, `::test_nist_example_validates_and_a_broken_one_does_not`, `tests/test_cli.py::test_gate_blocks_the_rsa_pr_and_writes_valid_oscal` |
| Policy blocks a seeded PR that adds RSA-2048 usage | **Met.** The gate fails with "CSNDPKB adds rsa-2048, which a large quantum computer can break", citing `src/batch/KEYGEN.cbl:14-15`, and `changeproof gate` exits 1 | `tests/test_gate.py::test_exit_check_policy_blocks_a_pr_that_adds_rsa_2048` |

### Seeded pull requests

`tests/fixtures/gate/seed.py` reuses the Week 5 billing platform (`general` market), adds three rules
to its `policy:` and makes five commits:

| Pull request | Expected | Result |
|---|---|---|
| Add an RSA-2048 key (`CSNDPKB` with `'RSA-PRIV'` and a 2048-bit modulus) | blocked | blocked (`test_exit_check_policy_blocks_a_pr_that_adds_rsa_2048`) |
| Add a SHA-384 digest (`CSNBOWH`) | passes | passes (`test_a_pr_that_adds_sha_384_passes_the_crypto_rule`) |
| Grow the RSA key to 3072 bits | blocked: a new quantum-vulnerable key | blocked (`test_changing_an_rsa_key_size_is_new_quantum_vulnerable_crypto`) |
| A high-criticality change with one approver | blocked by `high-criticality-needs-two-approvers` | blocked (`test_a_high_criticality_change_needs_two_independent_approvers`) |
| A public-key call whose algorithm the program does not show | passes with a warning | passes with a warning (`test_a_public_key_call_with_no_readable_algorithm_warns_but_passes`) |

## Roadmap items

- [x] **OPA/Rego policies from `policy:`.** `src/changeproof/policies/` has
  `no-new-quantum-vulnerable-crypto` and `high-criticality-needs-two-approvers`. Their Rego unit
  tests pass under `opa test` (`tests/test_gate.py::test_rego_policy_unit_tests_pass`).
  `equivalence-required-outside-impact-set` is reported **not-evaluated** with the reason
  (`::test_rules_without_evidence_yet_are_reported_not_evaluated`), and `validate` rejects unknown
  rule IDs (`tests/test_cli.py::test_validate_rejects_an_unknown_policy_rule`). The engine builds
  the policy input, and every fact in it carries provenance
  (`::test_every_policy_input_fact_carries_provenance`). OPA runs offline as a separate process.
  The gate makes no network call from Python (`tests/test_offline.py::test_the_policy_gate_makes_no_network_calls`),
  and CI's network-namespace run covers the OPA process.
- [x] **OSCAL assessment-results export.** `changeproof gate --oscal <file>` writes OSCAL 1.1.2
  assessment results:
  - Each finding targets one policy rule and cites its observations. Observations carry `file:line`
    provenance (`::test_oscal_records_policy_findings_and_cited_evidence`).
  - The mapped framework controls are listed as reviewed. No control is ever marked satisfied,
    because that is the assessor's call (ADR 005).
  - The same run and time give the same document (`::test_oscal_output_is_reproducible`).
- [x] **CI job.** `docs/ci/changeproof-gate.yml` is a pull-request workflow template. It installs
  changeproof and OPA, checks the changeproof release signature (Week 6), runs the gate in a
  network namespace with no interfaces, and keeps the OSCAL file (`tests/test_ci_template.py`).
  This repository's CI now builds the same pinned OPA, so the gate tests run there.
- [x] **Reading the algorithm of a crypto call.** This was needed for the exit check. An ICSF
  call's algorithm and key size are read from the `VALUE` literals and moved literals that reach
  the data it is given, with the entities they came from in `algorithm_from`
  (`tests/test_cobol_crypto.py`). RSA, ECC, DSA and DH are marked quantum-vulnerable. A public-key
  service (`CSND...`) whose algorithm cannot be read is marked unknown. This is narrow on purpose;
  the full crypto inventory is still **planned** (Week 16).

The framework mapping now cites the gate tests for SOC 2 CC8.1, RTS Art. 17(1)(b) and (h), NIST
CM-3, SC-13 and CNSA 2.0. The rows' control numbers stay **unverified** as before.

The whole suite passes with sockets blocked: 333 tests.

## Outside facts (project rule 6)

| Reference | Status |
|---|---|
| NIST OSCAL 1.1.2 schema | bundled from the `oscal` npm package. Not yet compared with NIST's release asset, which could not be reached (`src/changeproof/oscal/NOTICE.md`) |
| NIST assessment-results example | read from usnistgov/oscal-content on 2026-10-01 |
| ICSF service `CSNDPKB` and rule-array keywords (`RSA-PRIV`, `ECDSA`, ...) | **unverified** (IBM ICSF Application Programmer's Guide), like the Week 2 service names |
| OPA 1.21.1 (Apache-2.0) | module and license read from the Go module proxy on 2026-10-01 |

## Open issues

- **OPA must be installed** wherever the gate runs, as git must be for `change` and `impact`.
- **Algorithm reading is literal-based.** Keys loaded from a dataset, or an algorithm chosen at run
  time, show as unknown, which is a warning rather than a block. The crypto inventory (Week 16)
  goes further.
- **Approver identity** comes from `Approved-by` trailers. Approvals in GitHub reviews or
  ServiceNow need an exported file (planned since Week 4).
- **The OSCAL import-ap** points to a back-matter description of the gate rules, not to a full
  OSCAL assessment plan.

## Decisions needed from the owner

None to merge. ADR 005 (policy gate and OSCAL) is proposed and goes in with this week, as the
workflow allows.
