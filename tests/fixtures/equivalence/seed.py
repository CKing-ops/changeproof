"""Builds the Week 9 repository: the three synthetic batch programs, then two changes to FEECALC.

`refactor` rewrites an ADD as a COMPUTE and must change no behaviour anywhere. `rate-change` raises
the personal fee rate on purpose, so FEECALC's behaviour changes and nothing else's does. With
`packed`, the import also holds a program whose linkage the driver cannot fill.
"""

import importlib.util
import shutil
from pathlib import Path

_spec = importlib.util.spec_from_file_location("change_seed", Path(__file__).resolve().parent.parent / "change" / "seed.py")
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
commit, edit, run = _helpers.commit, _helpers.edit, _helpers.run

BATCH = Path(__file__).resolve().parents[3] / "corpus" / "synthetic" / "batch"
AUTHOR = ("Priya Raman", "priya.raman@billing.example")
LEAD = "Dana Okafor <dana.okafor@billing.example>"
PACKED = """000001 IDENTIFICATION DIVISION.
000002 PROGRAM-ID. PKDCALC.
000003 DATA DIVISION.
000004 LINKAGE SECTION.
000005 01  LK-TOTAL                PIC S9(7)V99 COMP-3.
000006 PROCEDURE DIVISION USING LK-TOTAL.
000007 MAIN-PARA.
000008     IF LK-TOTAL < 0
000009         MOVE 0 TO LK-TOTAL
000010     END-IF
000011     GOBACK.
"""


# PURPOSE: CREATES THE REPOSITORY; RETURNS EACH CHANGE'S NAME WITH ITS COMMIT
def seed(root: Path, packed: bool = False) -> dict[str, str]:
    src = root / "src" / "batch"
    src.mkdir(parents=True)
    for program in sorted(BATCH.glob("*.cbl")):
        shutil.copy(program, src / program.name)
    if packed:
        (src / "PKDCALC.cbl").write_text(PACKED)
    run(root, "init", "-q", "-b", "main")
    shas = {"base": commit(root, AUTHOR, 1, f"LOAN-1: Import batch programs\n\nApproved-by: {LEAD}")}
    edit(src / "FEECALC.cbl", "ADD 40 TO LK-FEE", "COMPUTE LK-FEE = LK-FEE + 40")
    shas["refactor"] = commit(root, AUTHOR, 2, f"LOAN-2: Write the late fee as a COMPUTE\n\nApproved-by: {LEAD}")
    edit(src / "FEECALC.cbl", "LK-AMOUNT * 0.015", "LK-AMOUNT * 0.0175")
    shas["rate-change"] = commit(root, AUTHOR, 3, f"LOAN-3: Raise the personal fee rate\n\nApproved-by: {LEAD}")
    return shas
