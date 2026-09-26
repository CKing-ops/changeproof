# Third-party licenses

Every dependency, vendored file and corpus source, with its license. Only permissive licenses
(MIT, BSD, Apache-2.0, ISC, PSF) may be added. Nothing GPL, LGPL or AGPL is copied into this repo.
Versions are the ones pinned in `uv.lock` as of Week 1; licenses were read from each package's
installed metadata.

## Runtime (shipped)

| Package | Version | License |
|---|---|---|
| pydantic | 2.13.5 | MIT |
| pydantic-core | 2.46.5 | MIT |
| annotated-types | 0.8.0 | MIT |
| typing-extensions | 4.16.0 | PSF-2.0 |
| typing-inspection | 0.4.4 | MIT |
| PyYAML | 6.0.3 | MIT |
| jsonschema | 4.26.0 | MIT |
| jsonschema-specifications | 2025.9.1 | MIT |
| referencing | 0.37.0 | MIT |
| rpds-py | 2026.6.3 | MIT |
| attrs | 26.1.0 | MIT |

## Development and CI only (not shipped)

| Package | Version | License |
|---|---|---|
| pytest | 9.1.1 | MIT |
| pytest-socket | 0.8.1 | MIT |
| pluggy | 1.6.0 | MIT |
| iniconfig | 2.3.0 | MIT |
| packaging | 26.3 | Apache-2.0 OR BSD-2-Clause |
| Pygments | 2.21.0 | BSD-2-Clause |
| hatchling (build backend) | >=1.27 | MIT |
| actions/checkout, astral-sh/setup-uv (CI) | v4, v6 | MIT |

## Parser spike only (`spike/`, not shipped, built into git-ignored `spike/_build/`)

| Component | Version / commit | License |
|---|---|---|
| tree-sitter (py-tree-sitter) | 0.26.0 | MIT |
| tree-sitter-cobol grammar | `550020dd` (yutaro-sakamoto/tree-sitter-cobol) | MIT |
| antlr4-python3-runtime | 4.13.2 | BSD-3-Clause |
| ANTLR tool jar (code generation, build time only) | 4.13.2 | BSD-3-Clause |
| Cobol85.g4 grammar | grammars-v4 `e199816b` | MIT (Ulrich Wolffgang / ProLeap) |

## Corpus

| Set | Source | License | In repo? |
|---|---|---|---|
| AWS CardDemo | aws-samples/aws-mainframe-modernization-carddemo `59cc6c2f` | Apache-2.0 (LICENSE and NOTICE kept) | yes, `corpus/carddemo/` |
| NIST CCVS85 COBOL test suite | `newcob.val` via the GnuCOBOL project's download mirror | US government work, public domain | no, fetched by `scripts/fetch_corpus.py` |

The GnuCOBOL compiler and its test tooling (`expand.pl` and friends) are GPL. None of it is in this
repo; the NIST splitter in `scripts/fetch_corpus.py` is our own code.
