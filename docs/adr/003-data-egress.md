# ADR 003: Data egress

- Status: proposed (Week 1), awaiting owner review
- Date: 2026-09-26
- Related: ROADMAP.md "Quantum data-egress guard", Week 10 (solver gate), Week 14 (bundle check),
  Week 20 (QPU package), CLAUDE.md rules 4 and 5

## Context

changeproof runs inside customer enclaves on code that may be proprietary, CUI or classified.
Most of the engine never needs a network. The one planned exception is optional cloud quantum
hardware (Week 20), which by nature sends a problem to a vendor. Even an "anonymized" optimization
problem can reveal system size and dependency topology. A single accidental call can spill CUI,
break an ATO boundary or lose a contract, so egress has to be impossible by default and
auditable when allowed.

## Decision

### What may leave, and what never leaves

| Data tier | Local classical | Local quantum simulator | Cloud QPU |
|---|---|---|---|
| Public / open-source / synthetic | yes | yes | yes, sanitized QUBO only |
| Customer unclassified (non-public) | yes | yes | only sanitized QUBO **and** written customer approval recorded in config **and** an approved vendor |
| CUI | yes | yes | never (unless the QPU is inside the customer's authorized boundary) |
| Classified | yes | yes, inside the enclave | never |

Customer code, IR, graphs, test data and evidence **never** leave, under any setting. The only
thing that may ever leave is an abstract numeric problem (a QUBO or Ising matrix) that has passed
the sanitizer.

### Enforcement

1. **Default deny in config.** `egress.allowed` defaults to `false`. A config that selects a
   remote solver backend (today: `qpu`) fails validation unless all of these hold:
   `egress.allowed: true`; `system.classification` is `unclassified`; at least one
   `egress.approved_vendors` entry; and for `data_tier: customer-unclassified`, a
   `customer_approval_ref`. A `cui` system can never set `egress.allowed: true`. Under the
   `cnsa2` profile, `require_pq_transport` cannot be turned off.
   Proven: `src/changeproof/egress.py::check_egress`, called from `Config` validation
   (`tests/test_egress.py::test_qpu_egress_matrix`, `tests/test_config.py::test_qpu_backend_fails_while_egress_is_denied`,
   `::test_cui_system_can_never_allow_egress`, `::test_egress_is_denied_when_section_is_missing`).

2. **One rule set, two gates.** The Week 10 solver interface calls the same `check_egress` before
   running any backend flagged `remote`, so a config edited after validation, or a backend chosen
   per run, still hits the same rules. **Planned** (Week 10).

3. **The engine package contains no network code.** No module under `src/changeproof/` may import
   `socket`, `ssl`, `http`, `urllib`, `asyncio`, `requests` or similar. The only network client
   will live in the separate optional `changeproof-qpu` package. Proven for the core:
   `tests/test_offline.py::test_engine_package_imports_no_network_modules`.

4. **Zero network calls in the default configuration.** The test suite runs with sockets blocked
   (pytest-socket), runs the default CLI flow under a Python audit hook that fails on any
   connect, bind or DNS lookup, and in CI runs the whole suite a second time inside a network
   namespace with no interfaces. Proven: `tests/test_offline.py::test_default_cli_flow_makes_no_network_calls`;
   CI job `ci.yml` step "Tests again inside a network namespace with no interfaces".

5. **Separate package, absent from the enclave bundle.** `changeproof-qpu` is never included in
   the air-gapped install. The Week 14 release pipeline fails if the bundle contains it or any
   network client library. **Planned** (Weeks 14 and 20).

6. **Problem sanitizer.** Before egress: strip names, paths, IDs and metadata; randomize variable
   order; optionally pad or split to hide size. The payload must pass a "no source-derived
   strings" test against the source tree's identifiers. **Planned** (Week 20).

7. **Egress attestation.** Every outbound call produces a signed record: payload hash,
   destination, time, approver, data tier and approval reference. **Planned** (Week 20).

8. **Post-quantum transport.** Outbound TLS must use a hybrid ML-KEM key exchange where the
   provider supports it; under `cnsa2` the call is refused otherwise. **Planned** (Week 20);
   the config rule that keeps `require_pq_transport` on is already enforced.

### Setup-time network use is separate

Fetching dependencies (`uv sync`) and fetching the corpus (`scripts/fetch_corpus.py`) happen at
setup, outside the engine, with pinned versions and SHA-256 checks. They are not analysis, and
they do not ship in the enclave bundle.

## Consequences

- A user who wants QPU trials must edit three or four explicit settings. That friction is
  intended.
- `REMOTE_BACKENDS` in `egress.py` is a fixed set until the Week 10 solver registry can tell the
  gate which backends are remote. Adding a remote backend before then means editing that set.
- Classification values in the schema are `unclassified` and `cui`. Classified systems are
  out of scope until a CMMC path exists; the table above still records the rule for them.
