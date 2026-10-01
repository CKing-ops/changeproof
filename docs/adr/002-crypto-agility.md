# ADR 002: Crypto agility

- Status: accepted by the owner on 2026-09-27 (Week 1)
- Date: 2026-09-26
- Markets: the decision applies to every market profile (ADR 004). The context below is written for
  `eu-dora`; the `us-defense` context (CNSA 2.0) is on branch `week-01-foundations`, and ADR 004
  lists the drivers for the `general` profile.
- Related: ROADMAP.md Week 6 (signer), Week 17 (production profile), CLAUDE.md rule 6

## Context

Every evidence record changeproof emits is signed. EU financial entities face two drivers that
make the signing algorithm a moving target:

- **DORA.** The RTS on the ICT risk management framework (Commission Delegated Regulation (EU)
  2024/1774) Art. 6(4) requires the encryption policy to provide "for updating or changing, where
  necessary, the cryptographic technology on the basis of developments in cryptanalysis", and
  Recital 9 names "threats from quantum advancements". Art. 7 covers key management through the
  full key lifecycle.
- **EU PQC roadmap.** The Coordinated Implementation Roadmap published by the NIS Cooperation
  Group on 23 June 2025 asks Member States to start the transition by end of 2026, to protect
  high-risk systems with PQC no later than end of 2030, and to finish as far as feasible by 2035.
  Finance counts among the vital sectors that roadmap puts first.

The RTS 2024/1774 references (Art. 6(4), Art. 7, recital 9) were checked against the EUR-Lex text on
2026-10-01; see `docs/framework-mapping.md` (Other outside references).

So the algorithms acceptable for evidence signatures will change at least twice: classical
(ECDSA P-384) to hybrid (classical + ML-DSA-87) to post-quantum only. Evidence has long retention
(DORA keeps ICT records for years and supervisors can ask for them), so records signed today must
stay verifiable after an algorithm is distrusted, and must be re-signable without being altered.

If algorithm names leak into schemas, predicates or business logic, each transition becomes a
schema migration across every stored record. That is the failure this ADR prevents.

## Decision

1. **One signer interface owns all cryptography.** Signing, verification and hashing go through a
   `Signer` / `Verifier` / `Hasher` interface (built in Week 6). No other module imports a crypto
   library or names an algorithm in code. CLAUDE.md rule 6 makes this a review rule. Built in
   Week 6 as `src/changeproof/signer/`; a test fails if any other module imports a crypto library
   (`tests/test_style.py::test_crypto_libraries_are_imported_only_by_the_signer`).

2. **Algorithms are opaque identifiers everywhere else.** Config, predicates and the IR carry
   algorithm IDs as strings matching `^[a-z0-9][a-z0-9-]*$` (e.g. `ml-dsa-87`, `ecdsa-p384`,
   `lms-sha256-192`, `sha-384`). Only the signer registry maps an ID to an implementation and
   decides whether it is allowed under the active profile. Proven: `Crypto` in
   `src/changeproof/config.py` validates shape only
   (`tests/test_config.py::test_crypto_algorithms_are_identifiers_not_a_closed_list`,
   `::test_crypto_algorithm_ids_must_be_well_formed`).

3. **Every signature records its algorithm ID.** Attestations use a DSSE envelope. Each entry in
   `signatures[]` carries, next to `sig` and `keyid`, the algorithm ID, the library and version
   that produced it, and a timestamp. Verification reads the algorithm from the record, never from
   current config, so old records verify under the algorithm they were signed with. The label is
   not trusted on its own: the algorithm must match the trusted key with that `keyid`. Proven:
   `tests/test_signer.py::test_every_signature_records_its_algorithm_library_and_time`,
   `::test_the_algorithm_comes_from_the_trusted_key_not_the_label`.

4. **Hybrid signing is several signatures, not a combined one.** A hybrid profile produces one
   DSSE signature per algorithm over the same payload. Verification policy says how many must
   hold and which algorithms are distrusted, so "valid if either component is still trusted" is a
   policy setting, not a format change. Proven:
   `tests/test_signer.py::test_exit_check_hybrid_verifies_when_either_component_is_distrusted`,
   `::test_a_distrusted_component_never_hides_tampering`, `::test_a_policy_can_require_an_algorithm`.

5. **Algorithm swap needs no schema change.** Adding or retiring an algorithm means registering
   or removing a signer implementation and editing `crypto:` in `changeproof.yaml`. Predicate
   schemas do not change. Digests are in-toto DigestSets (`{"<algorithm-id>": "<hex>"}`), which
   already allow several algorithms side by side. Proven for the schemas:
   `src/changeproof/predicates/schemas/common-v0.1.json` `$defs/digest`
   (`tests/test_predicates.py::test_example_predicates_validate`).

6. **Re-signing archived evidence countersigns; it never rewrites.** `changeproof resign` adds a
   new DSSE signature with the new algorithm to the existing envelope, over the unchanged payload,
   and keeps every earlier signature. The original bytes and their original signatures remain
   verifiable. A re-signing log records which records were countersigned, when and with what.
   It refuses evidence that does not verify. Proven:
   `tests/test_signer.py::test_resign_countersigns_without_altering_the_original`,
   `::test_resign_refuses_evidence_that_does_not_verify`. The archive job stays **planned** (Week 17).

7. **Profiles are named policies.** `crypto.profile` (`hybrid`, `nist-pqc`, `classical-legacy`)
   selects which algorithm IDs the signer registry will accept for signing and for verification.
   `hybrid` is the default because national agencies in the EU (for example Germany's BSI and
   France's ANSSI) advise hybrid classical + PQ schemes during the transition; recheck their
   current guidance before Week 6 (not rechecked in Week 6: the pages need the owner's approval to
   fetch, so this advice is **unverified**). The config stores the name; the registry owns the rule
   set, `src/changeproof/signer/profiles.py`, which also knows `cnsa2` for `us-defense`
   (`tests/test_signer.py::test_the_registry_checks_config_algorithms_against_the_profile`).
   One rule already applies at config time: under `hybrid` and `nist-pqc`,
   `egress.require_pq_transport` must stay true
   (`tests/test_config.py::test_hybrid_profile_requires_pq_transport`,
   `tests/test_egress.py::test_pq_profiles_keep_pq_transport`).

8. **Crypto inventory findings carry a migration category and deadline, not a US category.**
   `crypto-inventory/v0.1` findings record `migration_category` (e.g. `eu-pqc-roadmap:high-risk`)
   and `migration_deadline`, filled from the active profile. This feeds the DORA Art. 6(4) duty to
   show cryptography is updated as cryptanalysis develops.

## Consequences

- The config schema still accepts any well-formed ID (rule 8), and `changeproof validate` then checks
  each one against the signer registry and the profile, so a typo such as `ml-dsa-78` is caught
  (`tests/test_cli.py::test_validate_checks_algorithms_against_the_signer_registry`).
- The `changeproof init` template names algorithm IDs as config data. That is allowed by rule 6,
  which forbids them in code, not in configuration.
- Hybrid envelopes are larger: an ML-DSA-87 signature is 4,627 bytes, and a hybrid envelope over a
  4 KB statement is about 12 KB against about 6 KB for ECDSA alone
  (`scripts/signer_benchmark.py`, `docs/weekly/week06-signer-benchmark.json`).
- Certified modules can replace the open-source PQ library behind the same interface when
  available. For EU buyers that means Common Criteria or national certification (for example BSI)
  rather than, or as well as, FIPS 140-3 (Week 17).

## Alternatives considered

- **Composite (single) hybrid signature.** Smaller, but IETF composite formats were still
  drafts in 2026 and would bind the envelope format to one construction. Rejected for now;
  revisit when a composite ML-DSA standard is final.
- **Enumerate allowed algorithms in the config schema.** Gives early typo detection, but every new
  algorithm would then change a core schema, breaking rule 8. Rejected.
