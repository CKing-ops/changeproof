# ADR 005: Policy gate and OSCAL output

- Status: proposed (Week 7). The owner's workflow merges each week once its exit check passes, so
  this stands until the owner says otherwise.
- Date: 2026-10-01
- Related: ROADMAP.md Week 7, ADR 002 (crypto agility), ADR 003 (egress)

## Context

Week 7 needs policies written in OPA/Rego, run from the `policy:` list in `changeproof.yaml`, and an
OSCAL assessment-results export that validates. Analysis must stay offline (rule 4), facts come
only from parsers (rule 3), and every fact carries provenance (rule 2).

## Decision

1. **OPA runs as a separate process, like git.** `changeproof gate` writes the policy input to
   `opa eval` on stdin and reads the result. No Python Rego engine was available as a permissive
   wheel for this platform. OPA is Apache-2.0, is not shipped, and is found through
   `$CHANGEPROOF_OPA` or `PATH`. CI builds a pinned version with `go install`, and Go's checksum
   database checks it. The gate step in CI runs in a network namespace with no interfaces.
2. **Rules are bundled Rego packages.** One package per rule ID, under
   `changeproof.rules.<rule_with_underscores>`, with `deny` and `warn` sets of
   `{message, provenance}`. Rule unit tests run with `opa test`.
3. **The engine builds the policy input; Rego only judges it.** The input holds the changed crypto
   calls (with algorithm, key size and their values before the change), the components the change
   touched, and who approved and implemented it. Each fact cites where it came from. Rego never
   reads source code.
4. **A rule without evidence is `not-evaluated`, never passed.** `equivalence-required-outside-impact-set`
   reports `not-evaluated` until the equivalence attestation exists (Weeks 8-9). An unknown rule ID
   fails `changeproof validate`.
5. **OSCAL findings target policy rules, not framework controls.** Mapped controls go under
   `reviewed-controls`. Each finding's target is a rule (`objective-id`) marked satisfied or
   not-satisfied, citing its observations. The engine never states that a control is satisfied,
   because that judgment belongs to an assessor.
6. **OSCAL is validated against NIST's 1.1.2 schema, which is bundled.** Validation needs no
   network. The schema's two Unicode classes (`\p{L}`, `\p{N}`) are translated for Python's `re`
   (`src/changeproof/oscal/__init__.py`). UUIDs are name-based (RFC 4122 version 5), so the same
   run and time give the same document.

## Consequences

- Running `gate` needs OPA installed, as running `change` and `impact` needs git.
- Reading a crypto call's algorithm is a narrow, literal-based reader: the values and moved
  literals that reach the data a call is given. The full crypto inventory remains **planned**
  (Week 16). A public-key call whose algorithm cannot be read is a warning, not a block.
- The bundled schema came from the `oscal` npm package because NIST's release asset could not be
  reached from the build machine. It still needs comparing with NIST's file (see
  `src/changeproof/oscal/NOTICE.md`).

## Alternatives considered

- **Policies as Python.** This needs no OPA, but the ROADMAP names OPA/Rego, and Rego lets a
  customer write their own rules without changing the engine. Rejected.
- **OPA compiled to WebAssembly and run in-process.** Building the Wasm still needs the OPA binary,
  and a Wasm runtime would add a dependency. Revisit if installing OPA becomes a burden.
- **Validating with compliance-trestle.** It is Apache-2.0, but its dependencies include paramiko,
  which is LGPL. Rejected under the licensing rule.
