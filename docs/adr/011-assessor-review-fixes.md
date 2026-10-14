# ADR 011: Pack changes from the Week 13 assessor review

- Status: proposed (Week 13). Comes from a mock review, not an independent one
  (`docs/weekly/week13-review.md`); a real reviewer may change it.
- Date: 2026-10-07
- Related: ADR 002 (crypto agility), ADR 007 (equivalence), ADR 010 (evidence pack)

## Context

The Week 13 review read the evidence pack against SP 800-53A objectives, the RMF Assess and Monitor
outcomes and SSDF tasks. Its top five objections were about what the pack leaves the assessor to work
out: whether the release may go ahead, whether the changed code was tested, whether the stated crypto
profile is real, whether release signing happened, and which control each piece of evidence answers.

## Decision

1. **The report opens with a release decision** and an "open:" line for every failed, inconclusive
   or unevaluated rule, read from the policy-decision attestations.
2. **A fourth attestation per commit** reruns the characterization tests of every program, including
   those in the impact set (the existing behavioral-equivalence predicate with scope `full-suite`).
   The report shows, per program in the impact set, how many tests changed result. Inside the impact
   set a difference is expected; it is listed for the reviewer to check against the ticket. The
   gate's rule still uses the outside-impact-set run. The predicate schemas are unchanged.
3. **Keys must match the configured crypto section.** `pack` refuses signing keys that are not
   exactly `crypto.signing`, and a release key that is not `crypto.release_signing`. `pack-verify`
   fails when an algorithm the pack states has no valid signature, unless the verifier distrusts that
   algorithm, and when the pack statement's signatures differ from the ones its crypto block lists.
4. **`pack --release-key` countersigns the pack statement** with the release-signing algorithm (LMS
   in the sample profiles). Attestations stay signed with the evidence-signing algorithms only.
5. **The report maps evidence to controls** from the engine's framework table, with each control
   number's source status. It is engine code, like the rest of the report, so a pack still rebuilds
   byte for byte from its attestations with the same engine.

## Consequences

- A pack takes about twice as long to build, because every program is tested twice per commit.
- Packs built before this change rebuild differently (new report sections), as ADR 010 foresaw; the
  Week 12 sample pack was rebuilt by its script.
- Checking a control number at source changes the report of every later pack, which is intended:
  the report shows what was known when it was built.
