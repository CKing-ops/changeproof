# Week 4: change-centric input

- Market: universal build (`general` main path, `eu-dora` strong second)
- Branch: `week-04-change-input`, built on `week-03-dependency-graphs` (PR #6)
- Date: 2026-09-27
- Status: exit check met, including the owner-approved addition

## Exit check

| Check | Target | Result | Evidence |
|---|---|---|---|
| 10 seeded commits give complete who/what/when/where/how records | 10 of 10 | **Met: 10 of 10 records have no gaps** | `tests/test_change.py::test_exit_check_ten_seeded_commits_give_complete_records`; `scripts/change_exit_check.py` → `docs/weekly/week04-change-records.json` |

The seed (`tests/fixtures/change/seed.py`) builds a git repository of a synthetic SEPA batch system,
with fixed authors and dates. Each commit covers a different kind of change:

| # | Commit | Who (implementer / approver) | What | Why | Gaps | Open items |
|---|---|---|---|---|---|---|
| 1 | Import the SEPA batch programs | Ana Novak / Marc Dubois | 68 added | CHG0030001 | none | none |
| 2 | PAY-101: Round the SEPA fee before netting | Ana Novak / Marc Dubois | 2 modified | PAY-101 | none | no change request number |
| 3 | Add the overdraft limit to the account layout | Tomas Horvat / Marc Dubois | 1 added | CHG0030002 | none | none |
| 4 | [PAY-102] Count each account read for the audit total | Tomas Horvat / Ana Novak | 1 modified, 3 added | PAY-102 | none | no change request number |
| 5 | Move the account lookup under src/online | Tomas Horvat / Marc Dubois | no entity changed | CHG0030003 | none | no requester recorded |
| 6 | Point the nightly run at the version 2 account file | Ana Novak / Marc Dubois | 1 modified | CHG0030004 | none | none |
| 7 | Drop the audit count again | Tomas Horvat / Marc Dubois | 1 modified, 3 removed | PAY-102 | none | no change request number |
| 8 | Document where the fee rate comes from | Ana Novak / none | no entity changed | CHG0030005 | none | no requester recorded; no approver recorded |
| 9 | Skip zero-amount transactions in the totals | Ana Novak / Ana Novak | 1 modified | INC0045678 (emergency) | none | no requester recorded; an approver is also the implementer; no change request number |
| 10 | Switch the lookup hash to HMAC and add a readme | Tomas Horvat / none | 1 modified, 1 added, 1 removed | none | none | no requester recorded; no approver recorded; no change request number; change type not recorded |

"Complete" is `ChangeRecord.gaps()`:

- **who:** the implementer has a name and email;
- **when:** author and commit times;
- **where:** repository, commit and files;
- **what:** every changed file is either analyzed or listed with the reason it was not, and no
  parse failed;
- **how:** every text change has its hunk ranges.

"Open items" are change-control facts the repository does not hold. They are reported, not filled
in: commit 10 has no ticket, and the record says so.

Commits 5 and 8 show that a file move and a comment change no entity. Commit 3 changes only a
copybook, and the record follows it into `BATCH1`, which copies it. Commit 6 changes JCL, and the
record shows the DD's dataset before and after. Commit 10 swaps an ICSF one-way hash for an HMAC
call, which shows up as one crypto call removed and one added.

The whole test suite passes: 239 tests with sockets blocked.

## Roadmap items

- [x] **Diff to IR entities.** Both sides of each commit are checked out with `git archive` and
  parsed. COBOL and JCL entities are compared by id, so a moved line is not a change
  (`tests/test_change.py::test_what_is_field_level_for_a_statement_edit`,
  `::test_a_move_or_a_comment_changes_no_entity`, `::test_what_for_a_jcl_change`).
- [x] **Field-level lineage.** These statements become `flow` facts naming the fields read and
  written: `MOVE`, `COMPUTE`, `ADD`, `SUBTRACT`, `MULTIPLY`, `DIVIDE`, `READ INTO`,
  `WRITE`/`REWRITE FROM`, `STRING` and `UNSTRING` (`tests/test_cobol_flows.py`). The graph links
  fields with `flows-to` edges. `upstream()` and `downstream()` walk them, including through
  group moves (`tests/test_lineage.py`).
- [x] **Dynamic targets through moved literals.** A `CALL`, `XCTL`, screen or `TRANSID` through a
  data name now also resolves to every literal `MOVE`d into it
  (`tests/test_lineage.py::test_a_dynamic_call_resolves_through_a_moved_literal`).
- [x] **Who/when/where from git and CI.** Read from the raw commit object. Every fact cites
  `git-commit/<sha>:<line>`, the line in `git cat-file commit <sha>`. CI run details are copied
  only when the CI's own commit variable matches the commit
  (`::test_ci_details_are_kept_only_for_a_run_building_the_same_commit`).
- [x] **Why from trailers and tickets.** ServiceNow numbers (CHG, INC, PRB, RITM, REQ, CTASK) are
  taken from anywhere in the message. Jira-style keys are taken from trailers, the start of the
  subject, or square brackets, so ISO-27001 and SHA-256 are not mistaken for tickets
  (`::test_ticket_ids_are_copied_from_the_message_never_guessed`).
- [x] **`changeproof change <commit or range>`** prints the records as JSON, and exits 1 if any has
  a gap (`tests/test_cli.py::test_change_prints_a_record_per_commit`).

## Owner-approved addition: separate roles, emergency flag, change request

Approved by the owner on 2026-09-27 ("Add them", review thread), for DORA RTS Art. 17(1)(b)
(approval independent of implementation) and 17(1)(d) (purpose, scope, expected outcome).

- [x] **Requester, implementer and approver are kept apart.**
  - The implementer is the commit author.
  - The requester and approvers come from `Requested-by:` and `Approved-by:` trailers.
  - `independent` is false when an approver is the implementer, compared by email and otherwise
    by name. Commit 9 shows this.
  - Tests: `::test_who_keeps_requester_implementer_and_approver_apart`,
    `::test_an_approver_who_implemented_the_change_is_flagged`.
- [x] **Emergency flag.** Taken from a `Change-Type:` trailer (standard, normal, emergency). With
  no trailer, the flag is unknown, not false (`::test_missing_why_is_recorded_as_missing`).
- [x] **Change request.** The first ServiceNow change number the message names. The subject and
  its provenance hold the purpose.

## CardDemo with data flow

`scripts/graph_corpus_run.py` now also adds field nodes and `flows-to` edges. The results are in
`docs/weekly/week04-carddemo-graph.json`:

- 12,039 nodes (10,529 of them fields) and 6,780 edges;
- all 6,780 edges point at their statement (`edges_failing_check: []`);
- 3,273 `flows-to` edges, of which 2,879 resolve to a field in the program;
- 37 calls now resolve through moved literals, leaving 9 dynamic calls unresolved, down from 28.

The 394 unresolved flows name fields that live outside the corpus: CICS attribute bytes
(`DFHRED`, `DFHBMFSE`), `EIBCALEN`, `SQLCODE`, MQ structures and IMS `DIBSTAT`. Each comes from an
IBM copybook or control block that CardDemo does not ship.

The component marks from Week 3 now also show data moving between applications. Fields defined in
base-application copybooks are written by extension programs, and the reverse, in 146 `flows-to`
edges.

## Open issues

- **Approvals held outside git.** Pull-request reviews and ServiceNow approvals are not read. Both
  need the forge's or ticket system's API, which analysis must not call (no network). Importing an
  export file offline is **planned**.
- **Lineage between programs.** Lineage stops at `CALL ... USING`, `LINKAGE SECTION` and datasets.
  Following parameters and files between programs is **planned** for the Week 5 impact engine.
- **`REDEFINES` and conditions.** Lineage says what may flow, not what must: it does not narrow
  `REDEFINES` or which branch of an `IF` ran.
- **Entity text change.** Paragraph and statement text now ignores line layout. Week 2 text kept
  line breaks, so a paragraph after an insertion looked modified. The golden facts are unchanged.
- **Parsing speed** is unchanged: each side of a changed program is parsed again, with no cache
  until the Week 6 signer interface.
- **Fixture market.** The seed uses the `eu-dora` config from the Week 3 fixtures. Under the new
  rule, the next fixture starts with `general`.

## Decisions needed from the owner

None. Per the owner's 05:00 message, Week 4 merges once CI passes, and Week 5 starts from `main`.
