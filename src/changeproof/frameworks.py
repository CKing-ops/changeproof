"""Control mapping (ROADMAP Week 5): which engine evidence answers which control.

Market profiles name the frameworks; this module holds each framework's controls and the engine
outputs mapped to them. A control's ID and topic are outside facts (project rule 6): `checked` is
the date they were read in the source text itself, and None means unverified. An evidence row
names the test or exit check that proves the engine produces it, or "planned".
"""

from dataclasses import dataclass

PLANNED = "planned"


@dataclass(frozen=True)
class Source:
    title: str
    url: str
    checked: str | None = None  # ISO date the ID and topic were read in this source; None means unverified


@dataclass(frozen=True)
class Evidence:
    output: str  # the engine output, named as it appears in the predicate or change record
    proof: str  # pytest node ID or exit check that proves it, or PLANNED


@dataclass(frozen=True)
class Control:
    framework: str  # key used in MarketProfile.frameworks
    id: str
    topic: str  # our own short label for what the control is about, not its wording
    source: Source
    evidence: tuple[Evidence, ...]


AICPA_TSC = Source(  # RENAME: SOC 2 SOURCE
    "AICPA, 2017 Trust Services Criteria (with revised points of focus, 2022)",
    "https://www.aicpa-cima.com/resources/download/2017-trust-services-criteria-with-revised-points-of-focus-2022",
)
ISO_27001 = Source(  # RENAME: ISO/IEC 27001 SOURCE; THE STANDARD IS PAID, ISO PUBLISHES ONLY ITS CATALOGUE PAGE
    "ISO/IEC 27001:2022, Annex A (catalogue page; the text is sold by ISO)",
    "https://www.iso.org/standard/27001",
)
DORA = Source(  # RENAME: DORA REGULATION SOURCE
    "Regulation (EU) 2022/2554 (DORA), EUR-Lex",
    "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32022R2554",
)
DORA_RTS = Source(  # RENAME: DORA RTS ON ICT RISK MANAGEMENT SOURCE, ARTICLES 6, 7, 16, 17 AND RECITAL 9 READ
    "Commission Delegated Regulation (EU) 2024/1774, EUR-Lex",
    "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=OJ:L_202401774",
    checked="2026-10-01",
)
ECB_ITRQ = Source(  # RENAME: ECB IT RISK QUESTIONNAIRE SOURCE, CHECKED BY THE 2026-09-27 FACT-CHECK
    "ECB Banking Supervision, IT Risk Questionnaire 2026",
    "https://www.bankingsupervision.europa.eu/activities/srep/2026/html/ssm.srep_ITRQ2026.en.pdf",
    checked="2026-09-27",
)
NIST_800_53 = Source(  # RENAME: NIST SP 800-53 SOURCE
    "NIST SP 800-53 Rev. 5",
    "https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final",
)
NIST_SSDF = Source("NIST SP 800-218 (SSDF) v1.1", "https://csrc.nist.gov/pubs/sp/800/218/final")
NSA_CNSA2 = Source(  # RENAME: CNSA 2.0 SOURCE
    "NSA, Commercial National Security Algorithm Suite 2.0",
    "https://media.defense.gov/2022/Sep/07/2003071834/-1/-1/0/CSA_CNSA_2.0_ALGORITHMS_.PDF",
)

IMPACT = Evidence("impact predicate: changed and impacted entities, each with provenance",
                  "tests/test_impact.py::test_exit_check_recall_on_seeded_changes")
TIERS = Evidence("impact predicate: confidence tier and dependency path per impacted entity",
                 "tests/test_impact.py::test_every_impacted_entity_has_a_path_from_a_changed_entity")
RELIANT = Evidence("impact predicate: reliant_systems, from the component config",
                   "tests/test_impact.py::test_reliant_systems_come_from_the_config_with_their_line")
CROSSING = Evidence("graph: edges and shared resources marked where one component reaches another",
                    "tests/test_graph.py::test_resources_used_by_several_components_are_marked")
WHO = Evidence("change record: requester, implementer and approvers kept apart; self-approval flagged",
               "tests/test_change.py::test_an_approver_who_implemented_the_change_is_flagged")
WHY = Evidence("change record: ticket and change request copied from the commit, never guessed",
               "tests/test_change.py::test_ticket_ids_are_copied_from_the_message_never_guessed")
EMERGENCY = Evidence("change record: emergency flag from the Change-Type trailer",
                     "tests/test_change.py::test_missing_why_is_recorded_as_missing")
RECORD = Evidence("change record: who, what, when, where and how for every commit",
                  "tests/test_change.py::test_exit_check_ten_seeded_commits_give_complete_records")
CRYPTO = Evidence("impact predicate: touches_crypto when a change touches a crypto call",
                  "tests/test_impact.py::test_crypto_flag")
EQUIVALENCE = Evidence("behavioral-equivalence attestation for code outside the impact set (Weeks 8-9)", PLANNED)
SIGNED = Evidence("signed attestation, verifiable offline; hybrid signatures survive a distrusted algorithm",
                  "tests/test_signer.py::test_exit_check_hybrid_verifies_when_either_component_is_distrusted")
TEST_SELECTION = Evidence("test subset selected to cover the impact set (Week 10)", PLANNED)

CONTROLS = (
    Control("soc2", "CC8.1", "change management: changes are authorized, designed, tested, approved and implemented",
            AICPA_TSC, (RECORD, WHO, WHY, IMPACT, TIERS, EQUIVALENCE, SIGNED)),
    Control("iso-27001", "A.8.32", "change management", ISO_27001, (RECORD, WHO, WHY, IMPACT, RELIANT, SIGNED)),
    Control("iso-27001", "A.8.25", "secure development life cycle", ISO_27001, (IMPACT, CRYPTO, SIGNED)),
    Control("iso-27001", "A.8.28", "secure coding", ISO_27001, (CRYPTO,)),
    Control("iso-27001", "A.8.29", "security testing in development and acceptance", ISO_27001,
            (IMPACT, TEST_SELECTION, EQUIVALENCE)),
    Control("dora-rts-ict-risk", "Art. 17(1)(a)", "ICT change management: verification of whether ICT security "
            "requirements have been met", DORA_RTS, (IMPACT, CRYPTO, EQUIVALENCE)),
    Control("dora-rts-ict-risk", "Art. 17(1)(b)", "ICT change management: independence of the functions that approve "
            "changes from those that request and implement them", DORA_RTS, (WHO,)),
    Control("dora-rts-ict-risk", "Art. 17(1)(d)", "ICT change management: documentation of purpose and scope, "
            "timeline and expected outcomes", DORA_RTS, (WHY, RECORD, IMPACT)),
    Control("dora-rts-ict-risk", "Art. 17(1)(f)-(g)", "ICT change management: emergency changes, and their review "
            "and approval after implementation", DORA_RTS, (EMERGENCY, WHO)),
    Control("dora-rts-ict-risk", "Art. 17(1)(h)", "ICT change management: potential impact of a change on existing "
            "ICT security measures", DORA_RTS, (IMPACT, TIERS, CRYPTO)),
    Control("dora-rts-ict-risk", "Art. 16(2)-(3)", "ICT systems acquisition, development and maintenance: testing and "
            "approval before use and after maintenance; source code reviews", DORA_RTS,
            (IMPACT, TEST_SELECTION, EQUIVALENCE)),
    Control("dora", "Art. 9(4)(e)", "ICT change management procedures (cited by RTS 2024/1774 Art. 17(1))", DORA,
            (RECORD, IMPACT)),
    Control("dora", "Art. 28(3)", "register of information on ICT third-party contractual arrangements", DORA,
            (RELIANT,)),
    Control("ecb-itrq", "Q23c-e", "changes that caused issues, by cause: unexpected interdependencies between applications",
            ECB_ITRQ, (IMPACT, TIERS, CROSSING)),
    Control("ecb-itrq", "Q23c-e", "changes that caused issues, by cause: inadequate test coverage", ECB_ITRQ,
            (IMPACT, TEST_SELECTION, EQUIVALENCE)),
    Control("ecb-itrq", "Q23a", "emergency changes", ECB_ITRQ, (EMERGENCY, WHO)),
    Control("nist-800-53-cm", "CM-3", "configuration change control", NIST_800_53, (RECORD, WHO, WHY, SIGNED)),
    Control("nist-800-53-cm", "CM-4", "impact analyses", NIST_800_53, (IMPACT, TIERS, RELIANT)),
    Control("nist-800-53-sc", "SC-12", "cryptographic key establishment and management", NIST_800_53, (CRYPTO,)),
    Control("nist-800-53-sc", "SC-13", "cryptographic protection", NIST_800_53, (CRYPTO,)),
    Control("nist-ssdf", "SP 800-218", "secure software development practices", NIST_SSDF, (RECORD, IMPACT, SIGNED)),
    Control("cnsa2", "CNSA 2.0", "quantum-resistant algorithms for national security systems", NSA_CNSA2,
            (CRYPTO, SIGNED)),
)

NOT_MAPPED = {  # RENAME: FRAMEWORKS A PROFILE NAMES THAT HAVE NO CONTROLS MAPPED YET, WITH THE REASON
    "eu-pqc-roadmap": "a roadmap with dates, not controls; mapped with the crypto inventory (planned, Week 16)",
    "gdpr": "applies to data egress (ADR 003), not to change evidence",
    "swft": "artifact list not yet read at source; mapped with the evidence pack (planned, Week 12)",
}
REFERENCES = (  # RENAME: OTHER OUTSIDE REFERENCES IN THE REPO, AS (WHERE, REFERENCE, SOURCE)
    ("src/changeproof/markets.py, src/changeproof/config.py, docs/adr/003-data-egress.md",
     "DORA Art. 28(3): register of information on ICT third-party arrangements", DORA),
    ("src/changeproof/markets.py, docs/adr/003-data-egress.md", "DORA Art. 30: contract states where data is processed",
     DORA),
    ("src/changeproof/markets.py", "GDPR Chapter V: transfers of personal data to third countries",
     Source("Regulation (EU) 2016/679 (GDPR), EUR-Lex",
            "https://eur-lex.europa.eu/legal-content/EN/TXT/HTML/?uri=CELEX:32016R0679")),
    ("docs/adr/002-crypto-agility.md, docs/adr/003-data-egress.md",
     "RTS 2024/1774 Art. 6 (encryption and cryptographic controls) and 6(4) (updating cryptography on the basis of "
     "developments in cryptanalysis)", DORA_RTS),
    ("docs/adr/002-crypto-agility.md", "RTS 2024/1774 Art. 7: cryptographic key management", DORA_RTS),
    ("docs/adr/002-crypto-agility.md", "RTS 2024/1774 recital 9: threats from quantum advancements", DORA_RTS),
)


# PURPOSE: THE CONTROLS MAPPED FOR ONE FRAMEWORK, IN ORDER
def controls_for(framework: str) -> list[Control]:
    return [c for c in CONTROLS if c.framework == framework]
