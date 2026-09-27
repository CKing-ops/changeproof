# ADR 004: Market profiles

- Status: accepted by the owner on 2026-09-27 (Week 1, universal version)
- Date: 2026-09-27
- Related: ADR 002 (crypto agility), ADR 003 (data egress), `src/changeproof/markets.py`,
  `spike/mainstream_spike.py`

## Context

Week 1 was built twice, for US national security (PR #1) and for EU financial firms under DORA
(PR #2). Comparing the two showed that 91% of the code is the same; everything that differs sits
in `config.py` and `egress.py`, and it is all data: classification levels, which levels may never
send anything out, what customer-data egress must cite, and which frameworks the evidence maps to.

Keeping one branch per market would mean every fix lands twice. And most software companies,
regulated or not, already answer to change-management controls that ask for the evidence
changeproof produces:

- **SOC 2** common criterion CC8.1: changes are authorized, designed, developed, tested, approved
  and implemented under control.
- **ISO/IEC 27001:2022** Annex A 8.32 (change management), 8.25 (secure development life cycle),
  8.28 (secure coding) and 8.29 (security testing).

These are named here as anchors for Week 5's framework mapping. Nothing maps evidence to them yet.

## Decision

**One build with a `market:` setting.** A market profile is a frozen dataclass in
`src/changeproof/markets.py`, and `check_egress` takes the active profile. There are three profiles:

| Profile | For | Classifications | Never sends anything out | Customer data egress also needs | Frameworks (Week 5 targets) |
|---|---|---|---|---|---|
| `general` (default) | any software company | public, internal, confidential, restricted | restricted | `customer_approval_ref` | soc2, iso-27001 |
| `us-defense` | US national security | unclassified, cui | cui | `customer_approval_ref` | nist-ssdf, nist-800-53-cm, nist-800-53-sc, swft, cnsa2 |
| `eu-dora` | EU banks and payment firms | public, internal, confidential, restricted | restricted | `customer_approval_ref`, `ict_register_ref`, region `eea` or `adequacy` | dora, dora-rts-ict-risk, eu-pqc-roadmap, gdpr |

Proven:

- The profiles exist, are self-consistent, and each keeps at least one classification off the
  network (`tests/test_markets.py`).
- Each profile's egress rules hold, in 20 cases across the three markets
  (`tests/test_egress.py::test_qpu_egress_matrix`). The region rule applies only under `eu-dora`
  (`::test_region_rule_applies_only_to_dora`).
- `market:` defaults to `general`, and an unknown market is rejected. A classification from
  another market is rejected with the allowed list, and each market has its own default
  classification (`tests/test_config.py::test_market_defaults_to_general`,
  `::test_unknown_market_is_rejected`, `::test_classification_must_belong_to_the_market`,
  `::test_default_classification_follows_the_market`).
- `changeproof init --market <name>` writes a valid starter file for each market
  (`tests/test_cli.py::test_init_writes_the_chosen_market`).
- A sample config validates for each market (`docs/examples/changeproof.yaml`, `us-defense.yaml`,
  `eu-dora.yaml`; `tests/test_config.py::test_each_market_sample_validates`).

What changed to get there:

- `system.classification` is checked against the profile instead of a fixed enum.
- The data tiers `customer-unclassified` (US) and `customer-confidential` (DORA) become one tier,
  `customer`. The profile decides what it needs.
- `ict_register_ref` and `processing_region` stay in the schema for every market. Only `eu-dora`
  requires them.
- `require_pq_transport` stays locked on under the `cnsa2`, `hybrid` and `nist-pqc` crypto
  profiles in every market. Crypto profile and market are independent settings.

Adding a market later means adding one `MarketProfile` and its tests. No schema, adapter or
predicate changes (CLAUDE.md rule 8).

## How far the parser approach carries past COBOL

A universal market needs more languages than COBOL. `spike/mainstream_spike.py` parsed real,
permissively licensed code with the published tree-sitter grammars and counted a file as parsed
only with zero error nodes:

| Language | Sample | Files | Parsed clean | Lines | Lines per second |
|---|---|---|---|---|---|
| Java | Apache Commons Lang 3.17.0 | 500 | 500 (100%) | 182,246 | about 363,000 |
| Python | Python 3.12 standard library, tests excluded | 517 | 517 (100%) | 273,800 | about 319,000 |
| JavaScript | npm 10.9.7 as shipped with Node 22 | 1,054 | 1,053 (99.9%) | 147,752 | about 270,000 |

Raw results: `spike/results/mainstream.json`. The one JavaScript failure is `lib/base-cmd.js:166`,
a line that starts with an array spread. That this is a grammar gap is inferred and not checked
further.

What this shows: for mainstream languages, parsing is solved by off-the-shelf MIT grammars with no
preprocessor. COBOL is the hard case (ADR 001). What it does not show: a working adapter. Each
language still needs an adapter that turns the syntax tree into IR entities with provenance,
diffs them and runs tests. **Planned** and not scheduled; the ROADMAP names only the COBOL adapter
(Weeks 2 to 4), and a Python adapter sits in the parking lot.

## Consequences

- One branch serves all three markets. PRs #1 and #2 become reference points rather than the
  base for Week 2.
- Crypto deadlines differ by market (CNSA 2.0 for `us-defense`, the EU PQC roadmap for `eu-dora`).
  For `general` the nearest driver is NIST's proposed transition in IR 8547 (quantum-vulnerable
  signatures deprecated after 2030 and disallowed after 2035). That document was a draft when last
  checked and needs rechecking before Week 6. ADR 002's signer design does not change.
- Week 5 must map evidence to each profile's frameworks. The general profile's mapping (SOC 2,
  ISO 27001) is the one most buyers will ask for first.
- Market choice becomes a go-to-market decision, not a build decision.
