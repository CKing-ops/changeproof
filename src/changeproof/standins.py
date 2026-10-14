"""Stand-in sources for control numbers not yet read in their official text (owner's request, 2026-10-14).

Public reproductions, read so the product can be tested end to end before the owner uploads the
official texts. A control with a stand-in stays unverified; reports name the stand-in beside it.
To swap in the uploads: delete this file and tests/test_standins.py, drop the stand_in_for calls in
src/changeproof/pack/__init__.py and scripts/framework_mapping.py, and set `checked` on the source in
frameworks.py.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class StandIn:
    title: str  # the page and who publishes it
    url: str
    read: str  # ISO date the wording was matched on the page
    quote: str  # the control's wording or title as the page gives it


OSA_ISO = ("Open Security Architecture, ISO 27001:2022 Mappings (secondary)",
           "https://opensecurityarchitecture.org/frameworks/iso-27001-2022")  # RENAME: ISO ANNEX A TITLES READ HERE
STAND_INS = {  # RENAME: (FRAMEWORK, CONTROL ID) TO THE PUBLIC REPRODUCTION READ IN PLACE OF THE OFFICIAL TEXT
    ("soc2", "CC8.1"): StandIn(
        "KirkpatrickPrice, SOC 2 Academy: Change Management Best Practices (audit firm, secondary)",
        "https://kirkpatrickprice.com/video/soc-2-academy-change-management-best-practices/", "2026-10-14",
        "The entity authorizes, designs, develops or acquires, configures, documents, tests, approves, and implements "
        "changes to infrastructure, data, software, and procedures to meet its objectives."),
    ("iso-27001", "A.8.25"): StandIn(*OSA_ISO, "2026-10-14", "A.8.25 Secure development life cycle"),
    ("iso-27001", "A.8.28"): StandIn(*OSA_ISO, "2026-10-14", "A.8.28 Secure coding"),
    ("iso-27001", "A.8.29"): StandIn(*OSA_ISO, "2026-10-14", "A.8.29 Security testing in development and acceptance"),
    ("iso-27001", "A.8.32"): StandIn(*OSA_ISO, "2026-10-14", "A.8.32 Change management"),
    ("dora", "Art. 9(4)(e)"): StandIn(
        "Springlex, DORA regulation Art. 9 Protection and prevention (reproduction of OJ L 333, secondary)",
        "https://www.springlex.eu/en/packages/dora/dora-regulation/article-9/", "2026-10-14",
        "implement documented policies, procedures and controls for ICT change management, including changes to "
        "software, hardware, firmware components, systems or security parameters, that are based on a risk "
        "assessment approach and are an integral part of the financial entity's overall change management process, "
        "in order to ensure that all changes to ICT systems are recorded, tested, assessed, approved, implemented "
        "and verified in a controlled manner;"),
}


# PURPOSE: THE STAND-IN READ FOR A CONTROL, OR NONE
def stand_in_for(framework: str, control_id: str) -> StandIn | None:
    return STAND_INS.get((framework, control_id))
