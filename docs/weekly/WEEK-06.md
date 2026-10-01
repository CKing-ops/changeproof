# Week 6: crypto-agile signed attestations

- Market: universal build (`general` main path, `eu-dora` strong second, `us-defense` kept passing)
- Branch: `week-06-signer-interface`, built on `main` after Week 5 (PR #10)
- Date: 2026-10-01
- Status: exit check met; the outside facts behind the profile rules (CNSA 2.0, BSI and ANSSI advice,
  NIST IR 8547) are still **unverified** at source

## Why this week matters

The engine's claim is the link between what a change touches and proof that nothing else changed
behaviour. Week 6 makes that evidence signed and verifiable offline, years later, after an
algorithm falls. Impact statements can now be signed (`changeproof impact --key`); the equivalence
half is still **planned** (Weeks 8-9).

## Exit check

| Check | Result | Evidence |
|---|---|---|
| Tampering fails verification under every profile | **Met.** The four ROADMAP setups were each tried with a changed payload, a changed payload type and a flipped signature byte; every attempt fails. These setups are `classical` (ECDSA P-384), `ml-dsa-87`, `hybrid` (both) and `lms` | `tests/test_signer.py::test_exit_check_tampering_fails_under_every_profile` (4 cases) |
| Hybrid verification succeeds if either component is later distrusted per policy | **Met.** Distrusting ECDSA or ML-DSA-87 leaves the other signature holding. Distrusting both fails, and a distrusted component never hides tampering | `tests/test_signer.py::test_exit_check_hybrid_verifies_when_either_component_is_distrusted`, `::test_hybrid_fails_when_both_components_are_distrusted`, `::test_a_distrusted_component_never_hides_tampering` |
| Benchmark signature size and speed | **Done** (table below) | `scripts/signer_benchmark.py` → `docs/weekly/week06-signer-benchmark.json` |

### Benchmark

Medians of 20 runs over a 4 KB statement, on the build container (x86_64, Python 3.12). Key
generation is the median of 3 runs.

| Algorithm | Library | Signature | Public key | Sign | Verify | Key generation |
|---|---|---|---|---|---|---|
| `ecdsa-p384` | cryptography 50.0.2 | 103 B (DER, varies by a byte or two) | 120 B | 0.44 ms | 0.53 ms | 1.5 ms |
| `ml-dsa-87` | cryptography 50.0.2 | 4,627 B | 2,592 B | 1.8 ms | 0.36 ms | 1.7 ms |
| `lms-sha256-192` (height 10, W4) | pyhsslms 2.0.0 | 1,500 B | 48 B | 1,055 ms | 1.1 ms | 2,191 ms |

| Envelope | Size |
|---|---|
| ECDSA only | 5,868 B |
| ML-DSA-87 only | 11,899 B |
| Hybrid (ML-DSA-87 + ECDSA) | 12,253 B |
| LMS | 7,727 B |

LMS signing is slow because pyhsslms rebuilds the whole 1,024-leaf tree each time it loads a key.
That is acceptable for release signing, which happens once per release. Evidence signing uses
ML-DSA-87 and ECDSA.

## Roadmap items

- [x] **Signer interface with pluggable profiles.** `src/changeproof/signer/` is the only code that
  imports a crypto library (`tests/test_style.py::test_crypto_libraries_are_imported_only_by_the_signer`).
  - **Algorithms.** `ecdsa-p384`, `ml-dsa-87` (FIPS 204, pure, empty context) and `lms-sha256-192`
    (RFC 8554 / SP 800-208, SHA-256/192, height 10, W4) are registered by ID. `sha-384` is the
    evidence hash. `sha-256` is registered only to check upstream download pins
    (`scripts/fetch_corpus.py`), and every profile except `classical-legacy` rejects it for evidence.
  - **Profiles** are named rule sets, as ADR 002 decision 7 says. The ROADMAP's four setups are
    algorithm lists under them:

    | Profile | Evidence signing | Release signing |
    |---|---|---|
    | `hybrid` | needs a classical and a post-quantum algorithm | any |
    | `nist-pqc` | post-quantum only | post-quantum only |
    | `cnsa2` | needs post-quantum; classical may sit beside it during the transition | post-quantum only |
    | `classical-legacy` | needs classical | any |

    `changeproof validate` now checks every algorithm ID against the registry and the profile, so a
    typo such as `ml-dsa-78` is caught (`tests/test_cli.py::test_validate_checks_algorithms_against_the_signer_registry`,
    `tests/test_signer.py::test_the_registry_checks_config_algorithms_against_the_profile`,
    `::test_example_configs_pass_the_registry`). The config schema is unchanged, so new algorithms
    still need no schema change (rule 8).
- [x] **Open-source PQ library, recorded in every attestation.** ML-DSA-87 comes from `cryptography`
  50.0.2, whose wheel bundles OpenSSL 4.0.3. LMS comes from `pyhsslms` 2.0.0. These were picked over
  of liboqs because the liboqs Python bindings build or download the C library at first use, which
  breaks the offline rule. Each signature entry records `alg`, `keyid`, `library` (name and
  version) and `signed_at` (`tests/test_signer.py::test_every_signature_records_its_algorithm_library_and_time`).
  Those labels are not trusted on their own: the algorithm must match the trusted key, or
  verification fails (`::test_the_algorithm_comes_from_the_trusted_key_not_the_label`).
- [x] **Signing the engine's own releases.** `changeproof release <artifacts> --key <lms key>` signs an
  in-toto statement whose subjects are the artifacts' SHA-384 digests (new `release` predicate v0.1).
  `verify --subjects` checks the files still match (`tests/test_release.py`,
  `tests/test_cli.py::test_release_signs_artifacts_and_verify_checks_them`). Tried on this build:
  `uv build` produced the wheel and sdist, a throwaway LMS key signed them, and `verify` returned
  `ok`. The real release key and where it lives are **planned** (key custody, Week 17).
- [x] **`changeproof verify`** runs fully offline (`tests/test_offline.py::test_signing_and_verification_make_no_network_calls`).
  `--distrust` and `--require` set the policy. **`changeproof resign`** adds signatures over the
  unchanged payload, keeps every earlier signature byte for byte, refuses evidence that does not
  verify, and appends a line to a re-signing log
  (`tests/test_signer.py::test_resign_countersigns_without_altering_the_original`,
  `::test_resign_refuses_evidence_that_does_not_verify`, `tests/test_cli.py::test_keygen_sign_verify_and_resign`).
- [x] **SHA-384** for subject digests and key IDs (`tests/test_signer.py::test_digests_are_sha_384_digest_sets`).
- [x] **Signed impact evidence.** `changeproof impact <rev> --key ... --key ...` wraps the impact
  predicate in an in-toto statement whose subject is the head commit, then signs it
  (`tests/test_cli.py::test_impact_signs_its_statement_with_the_given_keys`).

Also proven: LMS is stateful, so the advanced key is written to disk before the signature is
returned. Two signatures use leaves 0 and 1, and the saved key shows 1,022 left
(`tests/test_signer.py::test_lms_state_is_saved_before_the_signature_is_returned`). Private keys
are written readable by their owner only (`::test_private_keys_are_written_owner_only`).

The framework mapping now cites `test_exit_check_hybrid_verifies_when_either_component_is_distrusted`
for "signed attestation" instead of **planned** (`docs/framework-mapping.md`).

The whole suite passes with sockets blocked: 306 tests.

## Design notes

- **One DSSE signature per algorithm** (ADR 002 decision 4). A verification holds when no trusted
  signature is invalid, at least one is valid, and every `--require`d algorithm is valid.
  Signatures from unknown keys do not count (`::test_signatures_from_unknown_keys_do_not_count`).
  Stripping the post-quantum signature from a hybrid envelope still verifies unless the policy
  requires `ml-dsa-87` (`::test_a_policy_can_require_an_algorithm`). A strict deployment should
  set `--require`.
- **Key ID** is the SHA-384 of the algorithm ID and the public key. A public key file whose ID does
  not match its content is refused.
- **New schema, no changed schema.** The `release` predicate is new; impact, equivalence,
  crypto-inventory and the config schema are unchanged.

## Outside facts (project rule 6)

| Reference | Where | Status |
|---|---|---|
| CNSA 2.0: SHA-384, ML-DSA-87, LMS preferred for software signing, classical allowed during the transition | `signer/profiles.py`, `signer/algorithms.py`, ROADMAP | **unverified** (NSA PDF needs the owner's approval to fetch) |
| BSI and ANSSI advise hybrid during the transition | ADR 002 decision 7 | **unverified**, not rechecked this week |
| NIST IR 8547 draft dates | ADR 004 | **unverified**, not rechecked this week |
| FIPS 204 (ML-DSA), RFC 8554 and SP 800-208 (LMS) | algorithm names | these are what the libraries implement. The libraries' own test vectors are not re-run here |

## Open issues

- **LMS key use from two processes at once** is not locked. One release signer at a time until a
  file lock or an HSM is added (**planned**, Week 17).
- **Release key custody.** No real release key exists yet. Where it lives (HSM, offline machine) is
  the owner's call when releases start. Nothing waits on it now.
- **Timestamps are the signer's own clock** and are not covered by the signature. A trusted
  timestamp is **planned** with the archive job (Week 17).
- **Parse cache.** The 2026-09-27 decision held the parse cache until the signer existed. It now
  can be built, but no week has it yet.
- **Unverified control numbers** from Week 5 are unchanged.

## Decisions needed from the owner

None to merge.
