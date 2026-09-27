# Week 1: repo, universal schemas, crypto-agility ADR, parser

- Market: US national security (primary market in ROADMAP.md)
- Branch: `week-01-foundations`
- Date: 2026-09-27
- Status: exit check run; parse rate met; ADRs waiting for owner review

## Exit check

| Check | Target | Result | Evidence |
|---|---|---|---|
| Corpus parses | ≥ 90% | **Met with ANTLR4 Cobol85: 481/503 (95.6%)**. tree-sitter-cobol: 442/503 (87.9%) | `spike/results/summary.md`, `spike/results/per_file.jsonl`, ADR 001 |
| Sample config validates | validates | **Met** | `tests/test_config.py::test_roadmap_sample_config_validates`, `::test_sample_config_validates_against_json_schema` |
| ADRs reviewed | owner review | **Waiting on owner** | `docs/adr/001-parser.md`, `002-crypto-agility.md`, `003-data-egress.md` |

The whole test suite passes: 69 tests with sockets blocked, and again inside a network namespace
with no interfaces (`unshare --net`).

## Roadmap items

- [x] Scaffolded `src/changeproof/`, `tests/`, `corpus/`, `docs/`, CI (`.github/workflows/ci.yml`)
  and an offline test mode (`--disable-socket` in `pyproject.toml`, plus a second CI run with no
  network).
- [x] `changeproof.yaml` JSON Schema and pydantic models, including `crypto:`, `optimization:` and
  `egress:`. The committed schema is generated from the models and a test fails if they drift
  (`tests/test_config.py::test_committed_json_schema_matches_models`).
- [x] `changeproof init`, plus `changeproof validate` and `changeproof schema` (`tests/test_cli.py`).
- [x] Adapter interface: `parse → IR`, `diff → entities`, `run → observations`, a registry, and a
  generic entity diff that ignores pure line moves (`tests/test_adapters.py`). Entities cannot be
  built without `file:line` provenance.
- [x] Draft predicates `impact/v0.1`, `behavioral-equivalence/v0.1`, `crypto-inventory/v0.1` as
  JSON Schemas, with an in-toto v1 Statement wrapper. Every fact in them requires provenance
  (`tests/test_predicates.py::test_every_fact_requires_provenance`).
- [x] ADR 002, crypto agility.
- [x] ADR 003, data egress. `egress.allowed: false` is the default, and the egress rules are enforced
  in config validation (`tests/test_egress.py`).
- [x] Test that the engine makes zero network calls in its default configuration
  (`tests/test_offline.py`).
- [x] Corpus and parser spike, written up as ADR 001.

## What I changed from the plan, and why

- **"GnuCOBOL samples" means the NIST CCVS85 suite.** The GnuCOBOL tarball holds almost no sample
  programs. GnuCOBOL's own test run uses the NIST suite, which is a US government work in the
  public domain. The suite is fetched from GnuCOBOL's download mirror with a pinned SHA-256 and is
  not committed. No GPL code is in the repo.
- **NIST placeholders are expanded by our own script**, following the suite's documented default
  behaviour. Without that step, placeholder lines such as `XXXXX084` are not valid COBOL.
- **Both parsers needed a preprocessor.** Neither handles `COPY`, `EXEC` blocks or separator commas
  alone. The spike's preprocessor becomes Week 2 adapter code.
- **`# PURPOSE:` tags are enforced by a test** (`tests/test_style.py`) for `src/`, `scripts/` and
  `spike/`. Test functions are exempt because their names state their purpose.

## Open issues for Week 2

- The ANTLR Python runtime is slow: about 100 lines per CPU-second, and 201 s for the largest
  CardDemo program. Week 2 caches IR by content hash. ADR 001 lists faster fallbacks.
- `COPY ... REPLACING` and `REPLACE` are not implemented yet. They cause 17 of the 22 ANTLR failures.
- Two programs hit Python's recursion limit.
- Algorithm IDs in `crypto:` are only shape-checked until the Week 6 signer registry exists.
- `main` on GitHub already held a README titled "The-Physics" and `MyPackages.py`
  (`pip install bloqade`). This branch replaces that README and leaves `MyPackages.py` untouched.
  bloqade is a quantum SDK (Part B territory), so it is not a changeproof dependency.

## Decisions needed from the owner

1. Review and approve ADRs 001, 002 and 003.
2. Accept ANTLR4 Cobol85 as the parser despite its speed cost, or ask for the tree-sitter fork
   route instead.
3. Choose the lead market. A DORA version of Week 1 is on branch `week-01-dora`, with its own
   report in `docs/weekly/WEEK-01-DORA.md`.
