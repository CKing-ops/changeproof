# changeproof

Semantic change evidence engine. See `ROADMAP.md` for the build plan and `CLAUDE.md` for working rules.

## Status

Week 1 (planned capabilities are labeled; proven ones cite their test):

- `changeproof init` writes a starter `changeproof.yaml` (`tests/test_cli.py`).
- `changeproof validate` checks a config against the schema (`tests/test_cli.py`).
- Default configuration makes zero network calls (`tests/test_offline.py`).
- Impact, equivalence and crypto-inventory evidence: **planned** (Weeks 5, 9, 16).

## Development

```sh
uv sync
uv run pytest
```
