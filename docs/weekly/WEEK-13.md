# Week 13: Assessor review

- Market: universal build (`general` main path, `eu-dora` strong second, `us-defense` kept passing)
- Branch: `week-13-review`, built on `main` after Week 12 (PR #18)
- Date: 2026-10-07
- Status: **exit check not met.** The owner chose a mock review; Week 13 closes only with a real
  reviewer's written statement.

## Exit check

| Check | Result | Evidence |
|---|---|---|
| Written statement on use or acceptance from a design partner | **Not met.** No outside reviewer yet. Claude reviewed the packs as a mock assessor at the owner's choice; that review is labelled unverified and is not a statement from a design partner | `docs/weekly/week13-review.md` |

## Roadmap items

- [x] **Three packs, one CNSA 2.0-signed.** The same synthetic release packed under `general` and
  `hybrid`, `eu-dora` and `hybrid`, and `us-defense` and `cnsa2`. The CNSA 2.0 pack carries ML-DSA-87
  signatures on every attestation and an LMS countersignature on the pack statement, and no
  classical signature (`tests/test_pack.py::test_the_cnsa2_pack_is_signed_with_post_quantum_algorithms_only`).
  Kept in `docs/weekly/week13-packs/`, built by `scripts/week13_packs.py`; CI verifies and rebuilds
  all three (`::test_the_three_week13_packs_kept_in_the_repository_verify_and_rebuild`).
- [ ] **Reviewed against SWFT/RMF criteria by a design partner.** Mock review only. RMF criteria were
  read at source (NIST CSRC RMF pages; SP 800-53A objectives in NIST's OSCAL catalog). SWFT criteria
  could be read only in press reports, so they stay unverified.
- [x] **Fix the top five objections**, each with a test first (`docs/weekly/week13-review.md`, ADR 011):
  1. Release decision and open findings on the cover (`::test_the_report_opens_with_the_release_decision_and_its_open_findings`).
  2. Tests of the changed programs, and what the change altered in them
     (`::test_the_report_shows_the_tests_run_inside_the_impact_set_and_what_they_changed`).
  3. The stated crypto profile enforced when building and verifying
     (`::test_the_pack_refuses_keys_that_do_not_match_the_configured_signing`,
     `::test_a_pack_missing_a_signature_its_profile_states_fails_the_check`).
  4. The release-signing algorithm applied to the pack statement
     (`::test_the_pack_states_its_crypto_profile_and_the_algorithms_that_signed_it`).
  5. Controls mapped in the report, with each number's source status
     (`::test_the_report_maps_its_evidence_to_the_controls_in_scope`).

## Control numbers checked at source (project rule 6)

Read on 2026-10-07 (`tests/test_frameworks.py::test_the_sources_read_on_2026_10_07_are_checked_and_the_rest_stay_unverified`):

- **Checked:** NIST SP 800-53 CM-3, CM-4, SC-12, SC-13 (and CM-3(2), SA-10, SI-7(15), SR-4 for the
  review), with their SP 800-53A objectives, in NIST's OSCAL catalog (Rev. 5.2.0). NIST SP 800-218
  practices and tasks; the single SSDF row became PS.2.1, PS.3.1 and PW.8.2. GDPR Chapter V on
  EUR-Lex (consolidated text).
- **Still unverified:** DORA Art. 9(4)(e), 28(3) and 30. Their wording matches a reproduction of
  OJ L 333 on springlex.eu, but the EUR-Lex page is too long for the build's page reader, so the
  rows say where they were read and stay unverified. SOC 2 CC8.1 (the AICPA criteria are a download
  behind a sign-in). ISO/IEC 27001 (needs a copy of the standard).
- **Update 2026-10-14:** CNSA 2.0 checked in NSA's CNSA 2.0 FAQ (v2.1), which matches the `cnsa2`
  profile's ML-DSA-87, LMS and SHA-384 (`tests/test_frameworks.py::test_cnsa2_is_checked_in_the_nsa_faq_and_swft_says_what_its_memo_page_does_not_give`).
  The SWFT memo's date, signer and focus areas checked on the DoD CIO page; its vendor asks (SBOM,
  third-party assessment) are still in press reports only. The Internet Archive is blocked from the
  build, and the EUR-Lex PDF stops at Article 6, so DORA stays as it was.

`docs/framework-mapping.md` and the Week 5 source table carry these results.

The whole suite passes with sockets blocked: 483 tests.

## Open issues

- **No independent reviewer.** The exit check needs one; the mock review is not a substitute.
- **Objections 6 to 12 stay open** (`docs/weekly/week13-review.md`). The SBOM (objection 6) belongs
  to Week 14's bundle.
- **Packs take about twice as long to build** because every program is now tested inside and
  outside the impact set.
- **The Week 12 sample pack was rebuilt** with new keys, since its report changed.

## Decisions needed from the owner

- Who reviews the packs for real: a design partner or assessor who can give the written statement.
- Merged on 2026-10-14 (PR #19) at the owner's choice; Week 13 stays open until a real reviewer's statement arrives.
