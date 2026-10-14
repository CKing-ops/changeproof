"""Stand-in sources (owner's request, 2026-10-14): public reproductions used until the official texts are
uploaded. Delete this file together with src/changeproof/standins.py when they are."""

from pathlib import Path

from changeproof.frameworks import CONTROLS
from changeproof.pack import control_blocks
from changeproof.standins import STAND_INS

ROOT = Path(__file__).resolve().parent.parent


def test_each_stand_in_belongs_to_a_mapped_control_that_is_still_unverified():
    controls = {(c.framework, c.id): c for c in CONTROLS}
    assert set(STAND_INS) <= set(controls)
    assert all(controls[key].source.checked is None for key in STAND_INS)
    assert all(s.url.startswith("https://") and s.read and s.quote for s in STAND_INS.values())


def test_the_report_and_the_mapping_name_the_stand_in_and_keep_the_control_unverified():
    evidence = {"sha": {"policy-decision": {"frameworks": ["soc2", "iso-27001"]}}}
    lines = [text for _, text in control_blocks(evidence)]
    assert "SOC 2 CC8.1 (source unverified; stand-in read 2026-10-14 at kirkpatrickprice.com): " \
           "change management: changes are authorized, designed, tested, approved and implemented" in lines
    mapping = (ROOT / "docs" / "framework-mapping.md").read_text()
    row = next(line for line in mapping.splitlines() if line.startswith("| A.8.32 |"))
    assert "unverified; stand-in read 2026-10-14" in row and "opensecurityarchitecture.org" in row
