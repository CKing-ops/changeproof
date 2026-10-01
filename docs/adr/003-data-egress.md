# ADR 003: Data egress

- Status: accepted by the owner on 2026-09-27 (Week 1, universal version)
- Date: 2026-09-27
- Markets: all profiles in ADR 004. The rules below are the same for every market except where a
  row names a profile. The DORA context is kept because `eu-dora` is the strictest profile.
- Related: ROADMAP.md "Quantum data-egress guard", Week 10 (solver gate), Week 14 (bundle check),
  Week 20 (QPU package), CLAUDE.md rules 4 and 5

## Context

changeproof runs inside a bank's or payment firm's own environment, on core-banking and payments
code that is confidential and often touches personal data. Most of the engine never needs a
network. The one planned exception is optional cloud quantum hardware (Week 20), which by nature
sends a problem to a vendor.

For an EU financial entity, that call is an ICT third-party arrangement and possibly a data
transfer:

- **DORA Art. 28** makes the entity manage ICT third-party risk and keep a register of information
  on every contractual arrangement with an ICT third-party service provider (Art. 28(3)).
- **DORA Art. 30** requires the contract to state where data will be processed.
- **GDPR Chapter V** restricts transfers of personal data outside the EEA to countries with an
  adequacy decision or other safeguards.
- **RTS 2024/1774 Art. 6** requires encryption of data in transit, and Art. 6(4) requires crypto
  to keep pace with cryptanalysis, including quantum threats (Recital 9).

The article and recital numbers in this list are **unverified** against the regulation text; their
source links and check status are in `docs/framework-mapping.md` (Other outside references).

Even an "anonymized" optimization problem can reveal system size and dependency topology, which a
bank may treat as confidential. So egress has to be impossible by default and auditable when
allowed.

## Decision

### What may leave, and what never leaves

The active market profile (`market:` in the config, default `general`) supplies the system
classification levels and the extra conditions for customer data:

| Profile | Classifications (default first) | Never sends anything out | Customer data also needs |
|---|---|---|---|
| `general` | `internal`, `public`, `confidential`, `restricted` | `restricted` | `customer_approval_ref` |
| `us-defense` | `unclassified`, `cui` | `cui` | `customer_approval_ref` |
| `eu-dora` | `internal`, `public`, `confidential`, `restricted` | `restricted` | `customer_approval_ref`, `ict_register_ref`, `processing_region` of `eea` or `adequacy` |

| Data the problem is built from | Local classical | Local quantum simulator | Cloud QPU |
|---|---|---|---|
| Public / open-source / synthetic | yes | yes | yes, sanitized QUBO only, approved vendor |
| Customer (`data_tier: customer`, any non-public customer code or data) | yes | yes | only sanitized QUBO **and** the profile's conditions above |
| Any problem from a never-egress system (`restricted`, or `cui` under `us-defense`) | yes | yes | never |

Customer code, IR, graphs, test data and evidence **never** leave, under any setting. The only thing
that may ever leave is an abstract numeric problem (a QUBO or Ising matrix) that has passed the
sanitizer.

### Enforcement

1. **Default deny in config.** `egress.allowed` defaults to `false`. A config that selects a remote
   solver backend (today: `qpu`) fails validation unless `egress.allowed: true` and at least one
   `egress.approved_vendors` entry are set. For `data_tier: customer` it also needs the fields the
   market profile lists above. A never-egress system can never set `egress.allowed: true`. Under
   the `cnsa2`, `hybrid` and `nist-pqc` crypto profiles, `require_pq_transport` cannot be turned off.
   Proven: `src/changeproof/egress.py::check_egress`, called from `Config` validation
   (`tests/test_egress.py::test_qpu_egress_matrix`, 20 cases across the three markets;
   `tests/test_config.py::test_customer_data_egress_needs_approval`,
   `::test_dora_customer_data_egress_needs_approval_register_entry_and_eu_processing`,
   `::test_restricted_system_can_never_allow_egress`, `::test_egress_is_denied_when_section_is_missing`).

2. **One rule set, two gates.** The Week 10 solver interface calls the same `check_egress` before
   running any backend flagged `remote`. **Planned** (Week 10).

3. **The engine package contains no network code.** No module under `src/changeproof/` may import
   `socket`, `ssl`, `http`, `urllib`, `asyncio`, `requests` or similar. The only network client
   will live in the separate optional `changeproof-qpu` package. Proven for the core:
   `tests/test_offline.py::test_engine_package_imports_no_network_modules`.

4. **Zero network calls in the default configuration.** The test suite runs with sockets blocked
   (pytest-socket), runs the default CLI flow under a Python audit hook that fails on any
   connect, bind or DNS lookup, and in CI runs the whole suite a second time inside a network
   namespace with no interfaces. Proven: `tests/test_offline.py::test_default_cli_flow_makes_no_network_calls`;
   CI job `ci.yml` step "Tests again inside a network namespace with no interfaces".

5. **Separate package, absent from the on-premises bundle.** `changeproof-qpu` is never included in
   the offline install. The Week 14 release pipeline fails if the bundle contains it or any network
   client library. **Planned** (Weeks 14 and 20).

6. **Problem sanitizer.** Before egress: strip names, paths, IDs and metadata; randomize variable
   order; optionally pad or split to hide size. The payload must pass a "no source-derived
   strings" test. **Planned** (Week 20).

7. **Egress attestation.** Every outbound call produces a signed record: payload hash,
   destination, time, approver, data tier, register-of-information reference and processing
   region. This is the evidence an ICT risk function or supervisor would ask for under DORA
   Art. 28. **Planned** (Week 20).

8. **Post-quantum transport.** Outbound TLS must use a hybrid ML-KEM key exchange where the
   provider supports it; under `cnsa2`, `hybrid` and `nist-pqc` the call is refused otherwise.
   **Planned** (Week 20); the config rule that keeps `require_pq_transport` on is already enforced.

### Setup-time network use is separate

Fetching dependencies (`uv sync`) and fetching the corpus (`scripts/fetch_corpus.py`) happen at
setup, outside the engine, with pinned versions and SHA-256 checks. They are not analysis, and
they do not ship in the offline bundle.

## Consequences

- The config records references (approval, register entry) but cannot check them against the
  customer's actual approvals or register. The Week 20 egress attestation carries them so auditors can.
- `processing_region` is self-declared per vendor. Vendor review (`docs/qpu-vendors.md`, Week 20)
  must confirm it before a vendor goes on `approved_vendors`.
- `REMOTE_BACKENDS` in `egress.py` is a fixed set until the Week 10 solver registry can tell the
  gate which backends are remote.
- This is not legal advice. The DORA, RTS and GDPR mapping should be reviewed by the customer's
  compliance function; Week 5's framework mapping will cite articles in full.
