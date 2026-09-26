# ADR 002: Crypto agility

- Status: proposed (Week 1), awaiting owner review
- Date: 2026-09-26
- Related: ROADMAP.md Week 6 (signer), Week 17 (`cnsa2` profile), CLAUDE.md rule 6

## Context

Every evidence record changeproof emits is signed. Between now and 2035 the algorithms that are
acceptable for those signatures will change at least twice: classical (ECDSA P-384) to hybrid
(classical + ML-DSA-87) to post-quantum only, with LMS for release signing. Evidence has long
retention, so records signed today must stay verifiable after an algorithm is distrusted, and must
be re-signable without being altered.

If algorithm names leak into schemas, predicates or business logic, each transition becomes a
schema migration across every stored record. That is the failure this ADR prevents.

## Decision

1. **One signer interface owns all cryptography.** Signing, verification and hashing go through a
   `Signer` / `Verifier` / `Hasher` interface (built in Week 6). No other module imports a crypto
   library or names an algorithm in code. CLAUDE.md rule 6 makes this a review rule.

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
   current config, so old records verify under the algorithm they were signed with. **Planned**
   (Week 6).

4. **Hybrid signing is several signatures, not a combined one.** A hybrid profile produces one
   DSSE signature per algorithm over the same payload. Verification policy says how many must
   hold and which algorithms are distrusted, so "valid if either component is still trusted" is a
   policy setting, not a format change. **Planned** (Week 6 exit check).

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
   **Planned** (Week 6, and the Week 17 archive job).

7. **Profiles are named policies.** `crypto.profile` (`cnsa2`, `nist-pqc`, `hybrid`,
   `classical-legacy`) selects which algorithm IDs the signer registry will accept for signing
   and for verification. The config stores the name; the registry owns the rule set. One rule
   already applies at config time: under `cnsa2`, `egress.require_pq_transport` must stay true
   (`tests/test_config.py::test_cnsa2_profile_requires_pq_transport`).

## Consequences

- Algorithm IDs in config are not checked against a list until the Week 6 signer registry exists.
  Until then a typo such as `ml-dsa-78` passes `changeproof validate`. Week 6 adds the check.
- The `changeproof init` template names algorithm IDs as config data. That is allowed by rule 6,
  which forbids them in code, not in configuration.
- Hybrid envelopes are larger (ML-DSA-87 signatures are about 4.6 KB). Week 6 benchmarks size and
  speed.
- FIPS 140-3 validated modules can replace the open-source PQ library behind the same interface
  when available (Week 17).

## Alternatives considered

- **Composite (single) hybrid signature.** Smaller, but IETF composite formats were still
  drafts in 2026 and would bind the envelope format to one construction. Rejected for now;
  revisit when a composite ML-DSA standard is final.
- **Enumerate allowed algorithms in the config schema.** Gives early typo detection, but every new
  algorithm would then change a core schema, breaking rule 8. Rejected.
