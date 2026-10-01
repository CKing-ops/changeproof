# Week 11: Second adapter (Java)

- Market: universal build (`general` main path, `eu-dora` strong second, `us-defense` kept passing)
- Branch: `week-11-java`, built on `main` after Week 10 (PR #16)
- Date: 2026-10-01
- Status: exit check met

## Exit check

| Check | Result | Evidence |
|---|---|---|
| Impact runs on an open-source Java project | **Met** on Apache Commons Lang (Apache-2.0), pinned at `29ccc76`: 249 main source files, about 97,600 lines. All 16 commits in the fetched window that change main Java sources ran with no parse failure, every changed entity lies in a changed hunk of its file, and every one of the 145,144 edges of the head graph cites a line holding its anchor | `scripts/java_impact_check.py` writes `docs/weekly/week11-java-impact.json`; `tests/test_java_corpus.py` repeats the graph check and three representative commits in CI after `scripts/fetch_java_corpus.py` |
| No core schema changes | **Met** | `tests/test_java_impact.py::test_exit_check_the_java_adapter_needed_no_core_schema_change` pins the digests of `adapters/base.py`, `graph/model.py`, `provenance.py`, the predicate schemas and the config schema as they were at the start of the week |

Seeded check first: a synthetic payments service (`tests/fixtures/java/system`, market `general`)
with six seeded commits. Changed and impacted entities were marked by hand in
`tests/fixtures/java/expected.json` before the engine ran; all six match exactly
(`tests/test_java_impact.py::test_exit_check_seeded_java_changes_match_the_hand_marked_impact`).

Commons Lang, per commit (`week11-java-impact.json`):

| Commit | What it did | Changed | Impacted |
|---|---|---|---|
| `0d9bda8`, `07dd0ca`, `dcba60a`, `5d3c269` | Javadoc | 0 | 0 |
| `df4be6c` | Typos in comments | 0 | 0 |
| `f3b9aca` | Sort members | 0 | 0 |
| `f3de6a4`, `69cb996` | Add `@Deprecated` | 11, 19 methods | 46, 58 |
| `d2eff05` | Remove an unused `throws` | 1 method | 3 |
| `f92016c`, `ee20414` | Logic fixes | 41, 36 | 88, 55 |
| `50587e0` | Rename internals | 27 | 127 |
| `17c3208` | `secure()` now uses `new SecureRandom()` | 15, touches crypto | 137 |
| `328f2ae`, `666ad13`, `bfa3c06` | Add a new public method | 40, 38, 32 | 2, 4, 2 |

Each run takes 15-20 seconds, most of it parsing both revisions of the whole project.

The first run found faults, fixed before this report: 36 edges citing the wrong line (a Latin-1
byte that Python's `splitlines` counts as a line break, and the anchor of static initializers),
5 changed entities outside any hunk (facts inside a renamed method), annotation-only and
`throws`-only commits showing no change, and `SecureRandom::new` not tagged as crypto.

## Roadmap items

- [x] **Java adapter on tree-sitter-java.** `parse` gives classes (with records, enums, interfaces
  and nested types), methods, constructors, fields, imports, calls, field uses and crypto calls,
  each with `file:line` provenance (`tests/test_java_adapter.py::test_types_methods_and_fields_carry_their_lines`,
  `::test_records_constructors_inheritance_and_imports`, `::test_calls_and_field_uses_name_the_method_they_are_in`).
  Broken Java is refused with its line (`::test_broken_java_is_refused_with_its_line`).
- [x] **diff to entities.** Ids hold names and parameter types, never lines; a comment or a moved
  member is not a change (`::test_a_comment_or_a_moved_line_is_not_a_change`,
  `::test_ids_never_hold_a_line_number_and_every_fact_has_provenance`).
- [x] **JCA crypto tagging.** `getInstance`, `new` and method references on JCA classes, with the
  algorithm and key size (`::test_jca_calls_are_tagged_with_their_algorithm`,
  `::test_rsa_with_a_key_size_reads_as_quantum_vulnerable`). The Week 7 gate blocks RSA added in
  Java, naming the JCA class and algorithm, and passes a fee change (`tests/test_java_impact.py::test_the_gate_blocks_rsa_added_in_java`).
- [x] **Graph and impact.** Calls, field uses, `extends`, `implements` and crypto uses in the same
  graph, walk and impact predicate as COBOL (`::test_the_java_graph_resolves_calls_fields_and_inheritance`,
  `::test_every_java_edge_passes_the_provenance_check`, `::test_impact_paths_cite_java_lines`).
  The impact run behind `changeproof impact` reads `.java` files with no new flag
  (`tests/test_java_corpus.py`).

Ada or C are left for `us-defense` if it is reopened, as the roadmap says. ADR 009 records the design.

The whole suite passes with sockets blocked: 440 tests, 4 of which skip unless the Commons
Lang corpus has been fetched (CI fetches it).

## Outside facts (project rule 6)

- Apache Commons Lang is Apache-2.0 and the pinned commit is dated 2024-08-24, both checked
  against the fetched repository itself (`LICENSE.txt`, `git log`). It is fetched by
  `scripts/fetch_java_corpus.py`, never committed.
- tree-sitter and tree-sitter-java are MIT, read from each package's own metadata
  (`docs/licenses.md`).
- The JCA standard algorithm names follow Oracle's Java Security Standard Algorithm Names page:
  **unverified** (not opened this week).

## Open issues

- **Resolution without a compiler.** 9,945 of 120,613 call edges in Commons Lang (8.2%) stay
  unresolved and are listed in each impact statement. Generics, `var` from a method call, lambda
  parameter types and fields inherited from another file are the main causes (ADR 009).
- **Interface dispatch** reaches implementations through the class, not per method.
- **Key size** is read only from `initialize` or `init` on a declared variable with a literal.
- **Running Java for characterization and equivalence** is **planned**; Java changes have
  impact evidence only.

## Decisions needed from the owner

None to merge. ADR 009 is proposed and goes in with this week, as the workflow allows. Moving
equivalence for Java earlier than its roadmap slot would be the owner's call.
