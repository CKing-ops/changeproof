# Week 12: AI-agent changes and the assessor evidence pack

- Market: universal build (`general` main path, `eu-dora` strong second, `us-defense` kept passing)
- Branch: `week-12-pack`, built on `main` after Week 11 (PR #17)
- Date: 2026-10-01
- Status: exit check met

## Exit check

| Check | Result | Evidence |
|---|---|---|
| The pack reconstructs offline from attestations alone | **Met.** A two-commit release of the synthetic billing system was packed under the `hybrid` profile (ML-DSA-87 plus ECDSA P-384). Only `pack.dsse.json` and the six attestations were copied into an empty folder, with no repository. `pack-verify` verified every signature and rebuilt the PDF report and both OSCAL files, byte for byte equal to the originals, with sockets blocked | `tests/test_pack.py::test_exit_check_the_pack_reconstructs_offline_from_attestations_alone`; the CLI path in `::test_the_cli_builds_and_verifies_a_pack`; no network calls under an audit hook in `tests/test_offline.py::test_the_evidence_pack_and_the_mcp_server_make_no_network_calls` |

Also shown:
- Every file in the pack matches its signed digest
  (`tests/test_pack.py::test_a_complete_pack_verifies_and_every_file_matches_its_signed_digest`).
- Changing the report, an OSCAL file or an attestation fails the check (`::test_tampering_with_any_file_fails_the_check`).
- The hybrid pack still verifies with ECDSA distrusted (`::test_the_hybrid_pack_still_verifies_when_one_algorithm_is_distrusted`).
- A sample pack is kept in `docs/weekly/week12-pack/`, with its public keys in
  `docs/weekly/week12-pack-keys/` (built by `scripts/week12_sample_pack.py`). CI verifies and
  rebuilds it (`::test_the_sample_pack_kept_in_the_repository_verifies_and_rebuilds`).

## Roadmap items

- [x] **MCP server** with the four tools the roadmap names: `impact`, `lineage`,
  `equivalence_status` and `crypto_inventory`. `changeproof mcp` serves them as JSON-RPC over
  stdio, read-only and offline (`tests/test_mcp.py`, all eight tests). A real subprocess session
  starts, lists the tools and answers a ping
  (`::test_a_client_starts_a_session_over_stdio_and_lists_four_read_only_tools`). Bad arguments and
  unknown tools come back as errors an agent can read, not crashes
  (`::test_bad_arguments_and_unknown_tools_are_reported_not_raised`). The crypto inventory returns
  the existing crypto-inventory predicate from COBOL and Java crypto calls; migration categories
  and the CBOM are **planned** (Week 16).
- [x] **AI attribution in attestations.** An agent named in an `Assisted-by`, `Generated-by` or
  `AI-agent` trailer, or as a co-author at a known agent address, is recorded in the change record
  and in the impact attestation with role `agent` and the trailer's line
  (`tests/test_agents.py::test_the_change_record_names_the_agent_from_its_trailer`,
  `::test_the_impact_attestation_lists_the_agent_with_where_it_was_read`). A new rule,
  `agent-changes-need-independent-approval`, fails such a change when no independent approver is
  recorded (`::test_an_agent_change_needs_an_approver_who_did_not_implement_it`; Rego unit tests in
  `tests/policies/`).
- [x] **`changeproof pack <release>`**: signed attestations, a PDF report and OSCAL, with the crypto
  profile stated in the signed pack statement and in the report
  (`tests/test_pack.py::test_the_pack_states_its_crypto_profile_and_the_algorithms_that_signed_it`).
  For each change the report puts what it touches beside whether behaviour outside it stayed the
  same. It also says that the equivalence attestation is linked to that impact attestation by
  digest (`::test_the_report_joins_impact_and_equivalence_for_each_change`,
  `::test_the_equivalence_attestation_names_the_impact_attestation_beside_it`).

New predicates, added beside the existing ones, which are unchanged: `policy-decision` v0.1 (what
the rules saw and decided, so OSCAL rebuilds without the repository) and `evidence-pack` v0.1. The
Week 11 core-schema digest test still passes. The PDF is written by the engine itself
(`tests/test_pdf.py`). ADR 010 records the design.

The whole suite passes with sockets blocked: 470 tests.

## Outside facts (project rule 6)

- MCP protocol versions 2025-11-25, 2025-06-18, 2025-03-26 and 2024-11-05: read from the reference
  Python SDK 1.30.0 (`mcp/shared/version.py`, `SUPPORTED_PROTOCOL_VERSIONS`) installed for the check
  and then removed. The specification pages themselves were not opened: **unverified** against the
  spec.
- `noreply@anthropic.com` as an agent co-author address: the co-author trailer Claude Code is set
  up to add to commits, as given in this build's own instructions (this repository's commits leave
  it out by the owner's rule). Other vendors' addresses are not listed: **unverified**, for the
  owner to add.
- pypdf 6.19.0 is BSD-3-Clause, read from its metadata (`docs/licenses.md`). The MCP SDK was not
  added because it brings in `certifi` (MPL-2.0).

## Open issues

- **No third-party MCP client tried yet.** The server follows the reference SDK's versions and
  message shapes, and is tested with a scripted client.
- **Agents are found only when a commit names them.**
- **A pack rebuilds only with an engine whose report code matches.** The engine version is in the
  pack statement; if a later week changes the report, the sample pack is rebuilt by its script.
- **Equivalence covers COBOL linkage subprograms only** (Weeks 8-9 limits). Java changes in a pack
  get impact and policy evidence; their equivalence attestation has no tests, so it reads
  inconclusive.
- **Week 13 needs a design partner** to review three packs against SWFT/RMF criteria. That depends
  on the owner's contacts.

## Decisions needed from the owner

None to merge. ADR 010 is proposed and goes in with this week, as the workflow allows. Week 13 is an
assessor review that needs a real reviewer, so the build stops there unless the owner says otherwise.
