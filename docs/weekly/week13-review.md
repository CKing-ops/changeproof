# Week 13 mock assessor review (unverified)

- Reviewer: Claude, acting as a mock assessor at the owner's choice (decision card, 2026-10-07). This
  is **not an independent review**. The reviewer is the same system that built the engine, so the
  review is labelled **unverified** and it does not meet the Week 13 exit check, which needs a real
  reviewer's written statement.
- Packs reviewed: the Week 12 sample pack (`docs/weekly/week12-pack`, as it stood at the start of the
  week), then the three Week 13 packs in `docs/weekly/week13-packs/`:
  - `general-hybrid`: `general` market, `hybrid` profile (ML-DSA-87 and ECDSA P-384).
  - `eu-dora-hybrid`: `eu-dora` market, `hybrid` profile.
  - `us-defense-cnsa2`: `us-defense` market, `cnsa2` profile. ML-DSA-87 signs every attestation, and
    LMS (`lms-sha256-192`) countersigns the pack statement. No classical signature appears anywhere
    in it (`tests/test_pack.py::test_the_cnsa2_pack_is_signed_with_post_quantum_algorithms_only`).
- All three are the same synthetic two-commit release of the billing batch programs: a refactor made
  with an AI assistant and approved, then a fee-rate change co-authored by an agent with no approver.
  Public keys are in `docs/weekly/week13-packs/keys/`. CI verifies and rebuilds all three
  (`tests/test_pack.py::test_the_three_week13_packs_kept_in_the_repository_verify_and_rebuild`).

## Criteria and where they were read

| Criteria | Status | Source |
|---|---|---|
| RMF Assess step purpose and its eight outcomes; Monitor step purpose and its five outcomes | **checked 2026-10-07** | NIST CSRC: [Assess](https://csrc.nist.gov/projects/risk-management/about-rmf/assess-step), [Monitor](https://csrc.nist.gov/projects/risk-management/about-rmf/monitor-step); [SP 800-37 Rev. 2](https://csrc.nist.gov/pubs/sp/800/37/r2/final) (the PDF's task text, A-1 to M-7, did not fit the build's page reader) |
| SP 800-53A assessment objectives for CM-3, CM-3(2), CM-4, SA-10, SC-13, SI-7(15), SR-4 | **checked 2026-10-07** | [NIST OSCAL catalog, SP 800-53 Rev. 5.2.0 with SP 800-53A](https://raw.githubusercontent.com/usnistgov/oscal-content/main/nist.gov/SP800-53/rev5/json/NIST_SP-800-53_rev5_catalog.json) |
| SSDF PS.1, PS.2, PS.3, PW.7, PW.8, RV.1 and tasks PS.2.1, PS.3.1, PS.3.2, PW.8.2 | **checked 2026-10-07** | [NIST SP 800-218](https://nvlpubs.nist.gov/nistpubs/SpecialPublications/NIST.SP.800-218.pdf) |
| SWFT: SBOMs from sandbox and production with a third-party SBOM; base risk scores on the DoD's 12 characteristics; artifacts loaded into eMASS; third-party verification of SP 800-218 | **unverified**: the DoD CIO memo (dated 24 April in Federal News Network's May 2025 report, signed by the acting DoD CIO) and the RFIs did not open from the build (403). Read only in press reports | [Federal News Network](https://federalnewsnetwork.com/defense-main/2025/05/arrington-kicks-off-effort-to-eliminate-rmf-for-dod-software/), [DefenseScoop](https://defensescoop.com/2025/04/29/dod-cio-katie-arrington-swift-software-acquisition-ato/), [GovCIO Media](https://govciomedia.com/pentagon-swft-rfis-back-shift-to-continuous-software-authorization/) |
| CNSA 2.0 algorithm list and dates | **unverified**: the NSA page refused the build (403) | [NSA](https://media.defense.gov/2022/Sep/07/2003071834/-1/-1/0/CSA_CNSA_2.0_ALGORITHMS_.PDF) |

## Objections, most serious first

Each objection names the criterion it comes from. The first five were fixed this week, tests first;
the rest stay open.

| # | Objection | Criterion | Outcome |
|---|---|---|---|
| 1 | The report never says whether the release may go ahead. A failed rule on change 2 sits on page 2, with nothing on the cover listing what is still open. | RMF Assess outcomes "Remediation actions to address deficiencies in controls are taken" and "Plan of action and milestones developed"; CM-03b.[02] (approve or disapprove with impact analyses); CM-03c (change decisions documented) | **Fixed.** The report opens with a release decision and one "open:" line per failed, inconclusive or unevaluated rule, with its source line (`tests/test_pack.py::test_the_report_opens_with_the_release_decision_and_its_open_findings`) |
| 2 | The pack shows that code outside the change behaved the same, but shows no test of the changed code itself. An assessor cannot see that the change was tested, or what it altered. | CM-03(02)[01]-[03] (changes tested, validated and documented before they are finalized); SSDF PW.8.2 | **Fixed.** Each commit gets a fourth attestation, a full-suite run (existing behavioral-equivalence predicate, scope `full-suite`). The report lists, for each program in the impact set, how many tests ran and which ones changed result: 0 of 14 for the refactor, 5 of 14 for the fee-rate change, each to check against its ticket (`::test_the_report_shows_the_tests_run_inside_the_impact_set_and_what_they_changed`) |
| 3 | The crypto profile is stated but not enforced. A pack whose config says `cnsa2` could be signed with ECDSA alone and still print "Crypto profile: cnsa2". A signature could also be stripped from a hybrid pack and it still verified. | SC-13b (the types of cryptography required for each use are implemented) | **Fixed.** `pack` refuses keys that are not exactly the configured signing algorithms. `pack-verify` fails when a stated algorithm has no valid signature (unless the verifier distrusts it, which is what hybrid signing is for) and when the pack statement's signatures differ from the ones it lists (`::test_the_pack_refuses_keys_that_do_not_match_the_configured_signing`, `::test_a_pack_missing_a_signature_its_profile_states_fails_the_check`) |
| 4 | The profile names a release-signing algorithm (LMS), but nothing in the pack was signed with it. | SI-7(15) (software authenticated by cryptographic mechanisms before installation); SSDF PS.2.1 | **Fixed.** `pack --release-key` countersigns the pack statement with the configured release algorithm, and refuses a key of another algorithm. The report names the release signature, or says that none was applied (`::test_the_pack_states_its_crypto_profile_and_the_algorithms_that_signed_it`) |
| 5 | The assessor has to map the evidence to controls by hand, and cannot tell which control numbers the vendor has checked. | RMF Assess outcome "Security and privacy assessment plans developed"; CM-3, CM-4 objectives | **Fixed.** The report ends with the controls of every framework in the market's scope, whether each control number was read at source (with the date) or is unverified, and the engine evidence that answers it; frameworks with no mapping say why (`::test_the_report_maps_its_evidence_to_the_controls_in_scope`). New rows this week: CM-3(2), SSDF PS.2.1, PS.3.1 and PW.8.2 (`tests/test_frameworks.py::test_the_week13_controls_are_mapped_from_their_checked_text`) |
| 6 | No SBOM of the system under change, and none of the engine. | SSDF PS.3.2; SWFT (unverified, press only) | Open. The engine's SBOM and CBOM are **planned** for Week 14 |
| 7 | Equivalence covers COBOL linkage subprograms only. Programs that read files, Db2 or CICS show as untested, and the Week 9 mutation check had one false "equivalent" in 30. | CM-03(02)[01]; SSDF PW.8.2 | Open. Stubs for files, Db2 and CICS are **planned**; the report already says equivalence is evidence from tests, not a proof |
| 8 | Approvals come only from commit trailers. There is no link to the approval record in the change system. | CM-03b.[02]; CM-03c | Open. Reading GitHub and ServiceNow approval exports is **planned** (Week 4 note) |
| 9 | A changed test is listed by program, not by the lines it ran or the values it produced; the attestations hold only output digests. | CM-03(02)[03] | Open. The characterization suite records traced lines (Week 8); putting them and the inputs in the report is a small follow-up |
| 10 | The pack names the engine version, not a digest of the engine build that made it. | SR-04[01]; SSDF PS.3.2 | Open. Belongs with the signed Week 14 bundle |
| 11 | Impact analysis covers security impact. Nothing analyses privacy impact. | CM-04[02] | Open. Out of the engine's scope today; an assessor would need another source for it |
| 12 | Retention period and the change control board are organizational. | CM-03e, CM-03g | Not the engine's to answer; listed so the assessor knows the pack does not claim them |

## What the mock reviewer would accept today, and what it would not

- Accept, with the caveats above: the impact analysis per change (CM-4), the change records with
  separated roles and flagged agent participation (CM-3), the signed and offline-verifiable pack
  (SSDF PS.2.1, PS.3.1), and the test evidence inside and outside the impact set for linkage
  subprograms (CM-3(2), PW.8.2).
- Not accept yet: anything that needs an SBOM (SWFT, PS.3.2), equivalence for programs that use
  files or databases, and any claim against SOC 2, ISO/IEC 27001 or CNSA 2.0 control numbers, which
  are still unverified at source.
