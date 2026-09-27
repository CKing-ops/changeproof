# Semantic Change Evidence Engine — Build Plan v4 (for Claude Code)
### Core engine (Weeks 0–15) + Post-Quantum & Quantum track (Weeks 16–21) + 2026–2030 PQC roadmap

## Positioning

**Product:** An engine that, for every code change, produces signed, machine-verifiable evidence of:
1. **Impact**: what the change touches (programs, fields, data stores, jobs, interfaces, downstream consumers).
2. **Behavioral equivalence**: whether behavior outside the intended change was preserved.

Each evidence record answers **who / what / when / where / how** at code depth and links to **why** (ticket, requirement, approval), which the engine links but never invents.

**The gap it fills:** SBOM tools (Anchore, Lineaje, Manifest Cyber, NetRise, ReversingLabs) prove *what is inside* software. Process tools (Kosli, ServiceNow, GRC) prove a change was *approved and tested*. Neither proves *what a change actually does*. DoD's Software Fast Track (SWFT) is moving authorization toward continuous, machine-readable, per-change evidence.

**Post-quantum angle (new):** Between now and 2030, every defense system must migrate its cryptography. Each migration is a risky code change. The engine will find quantum-vulnerable crypto, show the impact of replacing it, and prove behavior was preserved afterward, with evidence signed in CNSA 2.0 algorithms. This turns a regulatory deadline into a recurring use case.

**Quantum computing angle (new, research-gated):** Optimization (test selection, change-risk ranking, migration sequencing) is built behind a solver interface. Quantum and hybrid QNN backends are added as benchmarked research, and marketed only on measured results.

**Strategy:** Complement, don't compete. Emit in-toto attestations, OSCAL and CycloneDX (SBOM/CBOM) that SBOM tools, assessors, Kosli and RMF tools consume.

---

## Market focus (narrow first)

One build serves every market through the `market:` setting (`general` default, `eu-dora`, `us-defense`; ADR 004). This section says which market is sold to first.

**First sales target: EU financial sector under DORA (owner decision, 2026-09-27).**
- **Buyer 1: ICT risk and change-management functions at EU banks and payment firms** running COBOL cores (DORA in force since 17 Jan 2025; ICT change management in the RTS on ICT risk management, Art. 17).
- **Buyer 2: Their internal audit teams and external auditors / Big 4 IT-audit practices** (distribution channel and trust moat, the role SWFT assessors play in the US market).
- **Buyer 3: Core-banking and payment software vendors** that must hand their bank customers change evidence.
- **Entry vehicles:** design-partner pilots with one bank or vendor, teaming with an audit firm. **Planned**, pending the DORA Week 0 interviews.

**Second: `general`** (SOC 2 CC8.1, ISO/IEC 27001 Annex A 8.32), once a mainstream-language adapter exists.

**Kept as a tested profile: US national security & government (`us-defense`).** Buyers and entry vehicles below are unchanged and can be revived if the Week 0 interviews favour them.
- **Buyer 1: SWFT third-party assessors and security assessment firms** (distribution channel and trust moat).
- **Buyer 2: Defense software vendors and small primes** seeking faster ATOs and facing CNSA 2.0 procurement gates.
- **Buyer 3: Program offices / software factories** maintaining legacy mission systems (COBOL, Ada, C/C++, Fortran) that must also migrate crypto by 2030–2033.
- **Entry vehicles:** DoD SBIR/STTR (reauthorized through Sept 30, 2031; FY2027 proposal caps and stricter foreign-risk screening), DIU, AFWERX, teaming with primes or assessment firms.

**Later:** SOX / FDA CSA.

**Moat targets:** (1) assessor acceptance, (2) deep legacy-language adapters (COBOL, Ada), (3) air-gapped, offline-first operation, (4) accumulated per-system baselines, (5) CNSA 2.0-native evidence plus PQC-migration proof, which few change-evidence tools offer.

**Compliance realities:**
- No CUI or classified code until you're on a CMMC Level 2 path. Pilot on unclassified, public or synthetic code.
- Deliver as offline software inside the customer's enclave (avoids FedRAMP/IL hosting at first).
- Map to NIST SSDF (SP 800-218), NIST 800-53 (CM-3, CM-4 change control/impact; SC-12, SC-13 cryptography), SWFT artifacts, CNSA 2.0.
- **Quantum hardware calls send data off-premises.** QPU backends may only ever run on public or synthetic data. Inside enclaves, use local simulators only.
- Iron Bank container hardening requires a government sponsor; pursue it once a program office sponsors you.

**Out of scope:** QKD / quantum networking hardware, code translation, web UI, own GRC workflow, org-wide infrastructure monitoring (SIEM territory).

---

## ⚠️ Quantum data-egress guard (priority control, built from Week 1)

**The risk:** Real quantum computers (IBM Quantum, AWS Braket, D-Wave and others) are cloud services. Using one means data *leaves* the customer's environment. For defense customers that can mean a CUI spill, a classified-data incident, a broken ATO boundary or a lost contract. Even an "anonymized" optimization problem can leak sensitive structure (system size, dependency topology, which components are critical).

**The rule:** the engine is offline by default, and nothing leaves unless every condition below is met. Customer code, IR, graphs and evidence **never** leave. Only an abstract numeric problem (a QUBO matrix) may leave, and only in the allowed tier.

| Data tier | Local classical | Local quantum simulator | Cloud QPU |
|---|---|---|---|
| Public / open-source / synthetic | ✅ | ✅ | ✅ (anonymized QUBO only) |
| Customer unclassified (non-public) | ✅ | ✅ | ⚠️ Only anonymized QUBO **and** written customer approval recorded in config **and** approved vendor |
| CUI | ✅ | ✅ | ❌ Never (unless the QPU sits inside the customer's authorized boundary, e.g. a government-owned on-prem system) |
| Classified | ✅ | ✅ (inside the enclave) | ❌ Never |

**How it's enforced (not just documented):**
1. **Default deny.** `optimization.backend: qpu` fails unless `system.classification` and a new `egress:` section explicitly allow it.
2. **Separate package.** The QPU backend is a separate optional package that is **not included** in the air-gapped/enclave install bundle, so it cannot be enabled there by accident.
3. **Problem sanitizer.** Before egress, strip names, paths, IDs and metadata; randomize variable order; optionally pad or split the problem to hide size; the result must pass a "no source-derived strings" test.
4. **Egress attestation.** Every outbound call produces a signed record: payload hash, destination, time, approver, data tier. Assessors can audit exactly what left.
5. **Post-quantum transport.** Outbound connections require TLS with a hybrid post-quantum key exchange (ML-KEM) where the provider supports it; otherwise the call is refused under the `cnsa2` profile.
6. **Simulator-first.** Quantum simulators run fully local and deliver most of the research value; real QPUs are only for validating simulator results on public or synthetic data.

```yaml
egress:
  allowed: false                        # default; must be explicitly enabled
  data_tier: public                     # public | synthetic | customer-unclassified
  approved_vendors: []                  # e.g. [ibm-quantum] after vendor review
  customer_approval_ref: null           # ticket/letter ID, required for customer-unclassified
  require_pq_transport: true
```

---

## Universal setup (designed universal, shipped narrow)

`changeproof.yaml` describes the system once; adapters do the rest. (Avoid branding the product "Manifest"; Manifest Cyber already uses that name.)

```yaml
version: 0.1
system:
  name: logistics-core
  owner: program-office-x
  classification: unclassified          # unclassified | cui (future)
components:
  - id: pay-batch
    path: src/cobol/pay
    language: cobol                      # selects the adapter
    criticality: high
    data_stores: [PAYDB, VSAM.PAYMAST]
    relied_on_by: [finance-reporting, partner-feed-A]
evidence:
  produce: [impact, behavioral-equivalence, crypto-inventory]
  outputs: [in-toto, oscal, cyclonedx-cbom, pdf]
crypto:
  profile: cnsa2                         # cnsa2 | nist-pqc | hybrid | classical-legacy
  signing: [ml-dsa-87, ecdsa-p384]       # hybrid during transition; classical dropped by 2030
  release_signing: lms-sha256-192        # engine's own release signing (CNSA 2.0 software signing)
  hash: sha-384
optimization:
  backend: classical                     # classical | quantum-sim | qpu (public/synthetic data only)
policy:
  - rule: high-criticality-needs-two-approvers
  - rule: equivalence-required-outside-impact-set
  - rule: no-new-quantum-vulnerable-crypto
frameworks: [nist-ssdf, nist-800-53-cm, nist-800-53-sc, swft, cnsa2]
```

**Universal pieces (built once, Weeks 1–10):** config schema, adapter interface, predicate schemas, **crypto-agile signer interface**, policy-as-code, framework mappings, **solver interface**, CLI.
**Specialized pieces (added one at a time):** language adapters, audience packs, crypto profiles, solver backends.
**Rule:** a new adapter, crypto algorithm or solver backend must never require changing core schemas.

---

## Working rules for Claude Code sessions
- Keep this file and `CLAUDE.md` in the repo root. `CLAUDE.md` states: Python 3.12, `uv`, `pytest`, tests first. Every fact carries `file:line` provenance. The LLM never creates graph facts. Every evidence artifact is reproducible offline. No network at analysis time. **No cryptographic algorithm is hard-coded outside the signer interface.** **No quantum backend result is reported without its classical baseline.**
- One week = one branch = one PR. Exit check results go in `docs/weekly/WEEK-NN.md`.

---

# PART A — Core engine (with PQ foundations pulled forward)

## Week 0 — Validate & recruit an assessor design partner (no code)
- [ ] **DORA first:** 12 conversations: 4 bank ICT-risk / change-management leads, 3 internal or external IT auditors, 3 core-banking engineers who maintain COBOL, 2 people who went through a DORA supervisory review. Same questions as below, with "DORA ICT change management" in place of ATO and "EU PQC roadmap" in place of CNSA 2.0.
- [ ] The US conversations below are optional and only needed to reopen `us-defense`.
- [ ] 12 conversations: 4 SWFT/security assessors, 3 defense vendor/prime software leads, 3 program-office engineers, 2 recent ATO participants.
- [ ] Ask about change evidence, rejected artifacts, AI-written changes, legacy languages, **and** "How is CNSA 2.0 / PQC migration hitting your programs? Who proves a crypto swap didn't break anything?"
- [ ] Identify 1–2 open SBIR/DIU/AFWERX topics on software assurance, ATO acceleration, legacy modernization or PQC migration.
- **Kill gate:** fewer than 4 of 12 name change-impact evidence as a real gap, or zero auditor interest → re-scope (fallback: `general` or `us-defense`).

## Week 1 — Repo, universal schemas, crypto-agility ADR, parser
- [ ] Scaffold `src/changeproof/`, `tests/`, `corpus/`, `docs/`, CI, offline test mode.
- [ ] `changeproof.yaml` JSON Schema + pydantic, including the `crypto:` and `optimization:` sections; `changeproof init`.
- [ ] Adapter interface (`parse → IR`, `diff → entities`, `run → observations`).
- [ ] Draft predicates `impact/v0.1`, `behavioral-equivalence/v0.1`, `crypto-inventory/v0.1`.
- [ ] **`docs/adr/002-crypto-agility.md`**: every signature records its algorithm ID; hybrid (classical + PQ) signing supported; algorithm swap without schema change; plan for re-signing archived evidence.
- [ ] **`docs/adr/003-data-egress.md`**: offline by default; data-tier table; what may and may never leave; enforcement design. Add the `egress:` section to the config schema with `allowed: false` as the default.
- [ ] Test: the engine makes zero network calls in its default configuration (run the test suite with networking disabled).
- [ ] Corpus (AWS CardDemo + GnuCOBOL samples) and parser spike → `docs/adr/001-parser.md`.
- [ ] `market:` profiles (`general`, `eu-dora`, `us-defense`) → `docs/adr/004-market-profiles.md`.
- **Exit check:** ≥90% parse; sample config validates; ADRs reviewed.

## Week 2 — Intermediate representation (COBOL adapter)
- [ ] IR models with provenance; copybook resolution.
- [ ] **Tag crypto-relevant calls** (e.g., calls to crypto services/modules, hashing, key handling) as IR entities so later weeks can inventory them.
- **Exit check:** 20 hand-checked facts, 100% correct provenance.

## Week 3 — Dependency graphs
- [ ] Call, PERFORM, copybook, file/table, JCL graphs (SQLite + NetworkX); unresolved edges reported; config metadata on nodes.
- [ ] Cover what COBOL analysers already show (programs, CICS transactions, Db2 tables, files, batch jobs), and flag edges that cross from one configured component to another: the "unexpected interdependencies between applications" the ECB IT Risk Questionnaire asks about.
- **Exit check:** every edge has provenance.

## Week 4 — Change-centric input
- [ ] Diff → IR entities; field-level lineage; who/when/where from git/CI; why from commit trailers/tickets (ticket IDs from ServiceNow/Jira-style change records, as DORA ICT change management expects).
- [ ] Keep requester, implementer and approver as separate identities (DORA RTS Art. 17(1)(b) independence), carry an emergency-change flag, and link the change-request ID for purpose, scope and expected outcome (Art. 17(1)(d)). All linked from existing records, never invented.
- **Exit check:** 10 seeded commits give complete who/what/when/where/how records.

## Week 5 — Impact engine + framework mapping
- [ ] `changeproof impact <range>` with confidence tiers, reliant systems/partners, and a flag when a change touches crypto entities.
- [ ] `docs/framework-mapping.md`, one section per market profile: DORA and its RTS on ICT risk management (Art. 17 change management) first; SOC 2 CC8.1 and ISO/IEC 27001 Annex A 8.25/8.28/8.29/8.32; NIST 800-53 CM-3/CM-4/SC-12/SC-13, SSDF, SWFT, CNSA 2.0. The DORA section also maps impact and equivalence evidence to the change-failure root causes the ECB IT Risk Questionnaire asks about (unexpected interdependencies, inadequate test coverage).
- **Exit check:** recall ≥95% on seeded changes.

## Week 6 — Crypto-agile signed attestations (PQ core, not optional)
- [ ] Signer interface with pluggable profiles: `classical` (ECDSA P-384), `ml-dsa-87` (FIPS 204), `hybrid` (both; the default during transition), `lms` (SP 800-208, for release/software signing).
- [ ] Use an open-source PQ library for now (e.g., liboqs / its Python bindings); record the library and version in every attestation.
- [ ] Sign the engine's own release artifacts per CNSA 2.0 software-signing guidance (LMS preferred; ML-DSA-87 allowed).
- [ ] `changeproof verify` (fully offline) and `changeproof resign` (countersign archived evidence with a new algorithm without altering the original).
- [ ] Hashing at SHA-384 per CNSA 2.0.
- **Exit check:** tampering fails verification under every profile; hybrid verification succeeds if either component is later distrusted per policy; benchmark signature size and speed.

## Week 7 — OSCAL output + policy gate
- [ ] OSCAL assessment-results export; CI job; OPA/Rego policies from `policy:`, including `no-new-quantum-vulnerable-crypto`.
- **Exit check:** OSCAL validates; policy blocks a seeded PR that adds RSA-2048 usage.

## Week 8 — Characterization tests (GnuCOBOL)
- [ ] Offline Dockerized GnuCOBOL; boundary inputs; golden outputs linked to source.
- **Exit check:** ≥1 test per extracted condition for 3 batch programs.

## Week 9 — Behavioral-equivalence attestation
- [ ] `changeproof equivalence` runs tests outside the impact set; signed attestation; 20-bug mutation check.
- **Exit check:** ≥85% caught. **Kill gate** under 60%.

## Week 10 — Optimization layer + solver interface (quantum-ready foundation)
- [ ] Solver interface: `solve(problem, backend)` with backends `classical` now, and `quantum-sim` / `qpu` reserved.
- [ ] **Egress gate built into the solver interface now**, before any quantum code exists: any backend flagged `remote` must pass the egress policy check or raise an error. Unit tests cover every data-tier combination.
- [ ] Problem 1: **regression test selection**. Pick the minimum test subset that covers the impact set (greedy + OR-Tools CP-SAT).
- [ ] Problem 2: **change-risk ranking**. Classical ML baseline (gradient-boosted trees on graph features: fan-in, criticality, churn, crypto-touch).
- [ ] Export both problems also as **QUBO / Ising** formulations (serialized), so quantum backends can consume them later.
- [ ] Benchmark harness: solution quality, runtime, cost, reproducibility; results stored per run.
- **Exit check:** selected subsets catch the same mutations as the full suite; QUBO export verified equivalent to the classical model on small instances.

## Week 11 — Second adapter (moat test)
- [ ] **Java adapter** (tree-sitter-java; 100% parse in the Week 1 spike): `parse → IR`, `diff → entities`, crypto-call tagging (JCA). Serves DORA banks (COBOL plus Java) and opens `general`. Ada or C only if `us-defense` is reopened.
- **Exit check:** impact runs on an open-source Java project; no core schema changes.

## Week 12 — AI-agent changes + assessor evidence pack
- [ ] MCP server (`impact`, `lineage`, `equivalence_status`, `crypto_inventory`); AI attribution in attestations.
- [ ] `changeproof pack <release>`: PDF + OSCAL + signed attestations, with the crypto profile stated.
- **Exit check:** the pack reconstructs offline from attestations alone.

## Week 13 — Assessor review
- [ ] Design partner reviews 3 packs against SWFT/RMF criteria, including a CNSA 2.0-signed pack; fix the top 5 objections.
- **Exit check:** written statement on use/acceptance.

## Week 14 — Package, pilot, proposal
- [ ] Air-gapped bundle (offline image, checksums, SBOM **and CBOM** of the engine, LMS/ML-DSA-signed). **Verify the QPU package and all network clients are absent from the bundle** (automated check in the release pipeline).
- [ ] 2–3 pilots on unclassified/synthetic code.
- [ ] SBIR/DIU proposal draft: core engine plus PQC-migration evidence as the Phase II expansion.

## Week 15 — Decision gate 1
- **Continue to Part B if:** assessor partnership, ≥1 paid pilot or letter of support, and a submitted proposal.
- **Otherwise:** pivot to DORA with the same engine, or pursue a partnership/acquisition with an SBOM or assessment company.

---

# PART B — Post-quantum & quantum track (after Gate 1)

## Week 16 — PQC migration evidence (flagship 2026–2030 feature)
- [ ] **Crypto inventory:** detect quantum-vulnerable crypto (RSA, ECDSA/ECDH, DSA, FFDH, SHA-1) across adapters: COBOL service calls, C/OpenSSL, Java JCA, config files, certificates in repo.
- [ ] Output a **CycloneDX CBOM** plus `crypto-inventory` attestation; classify each finding by CNSA 2.0 category and deadline.
- [ ] **Migration impact:** for each finding, show what replacing it affects (callers, data formats, key sizes, interfaces, partners).
- [ ] **Migration proof:** after the swap, run behavioral-equivalence and emit a signed "PQC migration evidence" pack.
- **Exit check:** on a seeded project, 100% of planted vulnerable-crypto uses found; a seeded migration breaks nothing, and a deliberately bad migration is caught.

## Week 17 — CNSA 2.0 production profile
- [ ] `cnsa2` profile: ML-DSA-87 signatures, LMS for software/release signing, SHA-384, AES-256 for evidence at rest; SLH-DSA excluded for national security systems (allowed in a `nist-pqc` civilian profile).
- [ ] Abstraction for swapping to **FIPS 140-3 validated modules** once available; track the CMVP queue in `docs/crypto-validation.md`.
- [ ] Evidence-archive re-signing job for long-retention records.
- **Exit check:** full pipeline runs under `cnsa2` offline; the profile report is suitable to attach to procurement responses.

## Week 18 — Quantum simulator backend (optimization)
- [ ] Implement the `quantum-sim` backend: QAOA on the Week 10 test-selection QUBO using a local simulator (Qiskit or PennyLane), plus a quantum-inspired/annealing-style heuristic for comparison.
- [ ] Benchmark vs OR-Tools on growing instance sizes: quality, runtime, scaling trend.
- **Exit check:** benchmark report generated automatically; the classical baseline is always shown alongside.

## Week 19 — Hybrid QNN research (change-risk prediction)
- [ ] Hybrid classical–quantum classifier (variational circuit or quantum kernel) on the Week 10 change-risk task, using public repos' history only.
- [ ] Compare against the gradient-boosted baseline with identical features, splits and seeds; report accuracy, calibration, cost and variance.
- **Exit check:** honest research note in `docs/research/qnn-change-risk.md`, whatever the outcome.

## Week 20 — QPU trials behind the egress guard (public/synthetic data only)
- [ ] Build the QPU backend as a **separate optional package** (`changeproof-qpu`), never part of the enclave bundle.
- [ ] Implement the problem sanitizer (strip names/IDs/metadata, randomize variable order, optional padding) and the "no source-derived strings" test.
- [ ] Emit a signed egress attestation for every outbound call (payload hash, destination, time, approver, data tier).
- [ ] Require post-quantum (hybrid ML-KEM) transport where the provider supports it; refuse under `cnsa2` otherwise.
- [ ] Vendor review checklist in `docs/qpu-vendors.md`: data retention, logging, jurisdiction, US-person access, government-cloud options.
- [ ] Run small public/synthetic instances on real hardware (e.g., IBM Quantum, AWS Braket, D-Wave hybrid solvers). Record queue time, cost, noise and quality vs simulator and classical.
- **Exit check:** automated red-team tests pass. The backend refuses CUI, classified and unapproved customer data; refuses when `egress.allowed` is false; and refuses when the sanitizer finds any source-derived string. Every allowed call has a verifiable egress attestation.

## Week 21 — Decision gate 2 (quantum claims)
- [ ] Publish the benchmark report (optimization + QNN).
- [ ] Marketing rule: say "quantum-ready" (true: the solver interface and QUBO export exist) and "CNSA 2.0 / post-quantum signed evidence" (true). Say "quantum advantage" **only** for a task where measured results beat the classical baseline at useful size.
- [ ] Keep quantum backends behind a feature flag; revisit each hardware generation.
- [ ] Positioning for defense buyers: "quantum computing is optional and off by default; your code never leaves; every outbound call is attested." Offer local-simulator mode as the default inside enclaves, and on-prem QPU integration only where a government-owned system sits inside the authorized boundary.

---

## 2026–2030 post-quantum product roadmap (beyond the 21 weeks)

| When | External milestone | Product milestone |
|---|---|---|
| **Q4 2026** | CNSA 2.0 already says software signing should support/prefer PQ; DoW PQC Strategy (June 2026) sets department gates | Hybrid + ML-DSA-87 + LMS signing in core (Week 6); engine releases signed per CNSA 2.0 |
| **Jan 1, 2027** | NSS procurement gate: new acquisitions must support CNSA 2.0 algorithms | `cnsa2` profile production-ready; publish a CNSA 2.0 support statement for procurement |
| **2027–2028** | PQC modules moving through FIPS 140-3 / CMVP validation | Swap to validated modules; PQC-migration evidence packs sold to programs and assessors |
| **2029** | Common planning buffer before 2030 deprecation | Classical-only profile marked legacy; evidence-archive re-signing offered as a service |
| **2030** | CNSA 2.0 exclusive use for software/firmware signing; NIST IR 8547 (draft) deprecates RSA/ECC; DoW support-by-2030 gate | Remove classical-only signing; hybrid only where policy allows; default `cnsa2` |
| **2031–2033** | DoW use-by-2031; CNSA 2.0 exclusive dates for OS, web, cloud, custom/legacy apps | PQC-migration evidence at scale for legacy systems (the COBOL/Ada adapters pay off) |
| **2035** | RSA/ECC disallowed per NIST draft timeline | All archived evidence countersigned in PQ algorithms |

Recheck these dates each quarter; NIST IR 8547 was still a draft as of mid-2026.

---

## Parking lot
- **Suggestion (not scheduled): quantum mode switch CLI.** Candidate for Week 10 or Week 20 if adopted.
  - `changeproof quantum status`: shows the current backend (classical / quantum-sim / qpu), whether the QPU package is installed, and whether egress is allowed and why.
  - `changeproof quantum enable --mode sim` / `changeproof quantum disable`: safely edit `optimization.backend` in `changeproof.yaml`.
  - Per-run override, e.g. `changeproof impact <range> --backend quantum-sim`, for benchmarking without changing the config.
  - `changeproof quantum enable --mode qpu`: a guided check of every egress requirement (package installed, `egress.allowed`, data tier, approved vendor, approval reference). It refuses in enclave/air-gapped builds and never bypasses the egress guard.
- Migration sequencing and service decomposition as further QUBO problems.
- Hardware roots of trust (TPM / confidential computing) attesting the engine itself.
- Audience packs: cyber insurers, M&A due diligence, enterprise procurement.
- **Python adapter (not scheduled).** Lets the engine analyze its own code (`parse → IR`, `diff → entities`), so changeproof can produce impact and equivalence evidence for its own releases. Trust story for assessors.
