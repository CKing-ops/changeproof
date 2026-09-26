# Corpus

Public, open-source or synthetic code only. No CUI or classified code.

| Set | Location | How it gets here | License |
|---|---|---|---|
| AWS CardDemo | `carddemo/` | committed, see `carddemo/SOURCE.md` | Apache-2.0 |
| NIST CCVS85 COBOL test suite | `nist/` | `uv run python scripts/fetch_corpus.py` (pinned SHA-256) | US government work, public domain |

`nist/` is git-ignored. Fetching is a setup step; analysis never touches the network.
