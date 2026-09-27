# CLAUDE.md — changeproof

changeproof is a semantic change evidence engine: for every code change it produces
signed, machine-verifiable evidence of **impact** and **behavioral equivalence**.
`ROADMAP.md` (build plan v4, repo root) is the source of truth for scope and sequencing.
Read it before starting any week.

## Stack
- Python 3.12. Package and env management with `uv` only (`uv sync`, `uv run`, `uv add`).
- Tests with `pytest`. Source in `src/changeproof/`, tests in `tests/`, sample code in `corpus/`, docs in `docs/`.

## Non-negotiable rules
1. **Tests first.** Write or update a failing test before the code that makes it pass.
2. **Provenance on every fact.** Every IR entity, graph node, graph edge and evidence claim carries
   `file:line` provenance back to the source it came from. A fact without provenance is a bug.
3. **The LLM never creates graph facts.** Facts come only from parsers and deterministic analysis.
   The engine links the *why* (ticket, requirement, approval); it never invents it.
4. **Offline and reproducible.** No network access at analysis time. Every evidence artifact must be
   reproducible offline from its inputs.
5. **Egress denied by default.** Nothing leaves the machine unless the `egress:` config section
   explicitly allows it (`egress.allowed: false` is the default). Customer code, IR, graphs and
   evidence never leave under any setting. See `docs/adr/003-data-egress.md`.
6. **Crypto only through the signer interface.** No cryptographic algorithm (signature, hash, KEM,
   cipher) is hard-coded outside the signer interface. Every signature records its algorithm ID.
7. **No quantum result without its classical baseline.** Any quantum or quantum-sim backend result
   is always reported next to the classical baseline on the same problem.
8. **Core schemas stay stable.** A new adapter, crypto algorithm or solver backend must never require
   a change to core schemas.

## Testing
- `uv run pytest` must pass with networking disabled. The suite includes a test that the engine
  makes zero network calls in its default configuration.
- Tests must not depend on external services.

## Workflow
- One roadmap week = one git branch = one PR (branch name `week-NN-<short-topic>`).
- Stop at each week's exit check. Record exit-check results in `docs/weekly/WEEK-NN.md`
  (what was done, exit-check evidence, open issues).
- Wait for the owner's approval before starting the next week.
- Do not start Part B (Weeks 16–21) or any parking-lot item unless the owner asks.

## Claims must be proven
- No capability is claimed in docs, README, weekly reports or proposals unless a passing test or
  exit check proves it. Cite the test or exit check next to the claim.
- Anything not yet proven is labeled **planned**.

## Compliance guardrails
- Use only public, open-source or synthetic code in `corpus/`. No customer or bank code, no personal
  data, no CUI or classified code.
- Architecture decisions go in `docs/adr/NNN-<topic>.md`.

## Licensing
- Check the license of every third-party dependency or snippet before adding it. Permissive
  licenses (MIT, BSD, Apache-2.0, ISC, PSF) only. Never copy GPL, LGPL or AGPL code into the repo.
- Log every dependency with its version and license in `docs/licenses.md`.
- GPL-licensed corpus samples are fetched by a pinned script, never committed.

## Comment and naming style
- Comments are plain and short, written in the project's own voice. No boilerplate docstrings.
- Every function gets a capitalized tag comment on the line above it:
  `# PURPOSE: PARSES A COPYBOOK AND RETURNS ITS FIELDS`
- Variables the owner may want to rename get a tag comment beside them, while the name itself
  keeps normal Python naming (`snake_case`, `UPPER_CASE` constants):
  `field_map = {}  # RENAME: FIELD NAME TO IR ENTITY LOOKUP`
- Keep the tags greppable (`grep -rn "# PURPOSE:\|# RENAME:" src/`). Editors can colour them with a
  comment-highlighting extension (e.g. Todo Tree or Better Comments), since source files have no colour.
- Commits carry no AI co-author or session trailers, and PR bodies carry no "Generated with"
  footer. PR bodies keep only the project attribution block at the top.

## Code style
- Write efficient, idiomatic Python, the way an experienced engineer on this team would.
- Comment only what the code can't say: intent, a non-obvious constraint, a provenance link.
  Never narrate the next line ("# loop over the fields") or restate a name.
- No emoji, no filler docstrings, no "This function..." preambles, no step-numbered comments.
- No over-defensive boilerplate: validate at boundaries (config load, adapter input), then trust
  types inside. No blanket `try/except Exception`, no redundant `None` checks, no unused
  parameters "for future use".
- Prefer small functions, standard library first, and precise names over explanatory comments.
