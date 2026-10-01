"""Builds the Week 7 exit-check repository: the Week 5 billing platform with policy rules, then
seeded pull requests, one commit each. The first adds an RSA-2048 key and must be blocked.
"""

import importlib.util
import shutil
from pathlib import Path

_spec = importlib.util.spec_from_file_location("impact_seed", Path(__file__).resolve().parent.parent / "impact" / "seed.py")
_impact = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_impact)
commit, edit, run, PRIYA, JONAS = _impact.commit, _impact.edit, _impact.run, _impact.PRIYA, _impact.JONAS

APPROVALS = "Approved-by: Dana Okafor <dana.okafor@billing.example>\nApproved-by: Lee Moreau <lee.moreau@billing.example>"
ONE_APPROVAL = "Approved-by: Dana Okafor <dana.okafor@billing.example>"
POLICY = """policy:
  - rule: no-new-quantum-vulnerable-crypto
  - rule: high-criticality-needs-two-approvers
  - rule: equivalence-required-outside-impact-set
"""

KEYGEN = """000001 IDENTIFICATION DIVISION.
000002 PROGRAM-ID. KEYGEN.
000003 DATA DIVISION.
000004 WORKING-STORAGE SECTION.
000005 01  WS-RC                   PIC S9(8) COMP.
000006 01  WS-REASON               PIC S9(8) COMP.
000007 01  WS-RULE-COUNT           PIC S9(8) COMP VALUE 1.
000008 01  WS-KEY-RULES            PIC X(8) VALUE 'RSA-PRIV'.
000009 01  WS-KEY-VALUES.
000010     05  WS-MODULUS-BITS     PIC 9(4) COMP VALUE 2048.
000011 01  WS-KEY-TOKEN            PIC X(2500).
000012 PROCEDURE DIVISION.
000013 KEY-PARA.
000014     CALL 'CSNDPKB' USING WS-RC WS-REASON WS-RULE-COUNT
000015          WS-KEY-RULES WS-KEY-VALUES WS-KEY-TOKEN
000016     GOBACK.
"""

DIGEST = """000001 IDENTIFICATION DIVISION.
000002 PROGRAM-ID. INVHASH.
000003 DATA DIVISION.
000004 WORKING-STORAGE SECTION.
000005 01  WS-RC                   PIC S9(8) COMP.
000006 01  WS-REASON               PIC S9(8) COMP.
000007 01  WS-RULE-COUNT           PIC S9(8) COMP VALUE 1.
000008 01  WS-HASH-RULES           PIC X(8) VALUE 'SHA-384'.
000009 01  WS-TEXT                 PIC X(80).
000010 01  WS-DIGEST               PIC X(48).
000011 PROCEDURE DIVISION.
000012 HASH-PARA.
000013     CALL 'CSNBOWH' USING WS-RC WS-REASON WS-RULE-COUNT
000014          WS-HASH-RULES WS-TEXT WS-DIGEST
000015     GOBACK.
"""


# PURPOSE: EACH SEEDED PULL REQUEST AS (NAME, AUTHOR, MESSAGE, EDIT TO APPLY TO THE WORK TREE)
def changes(root: Path) -> list:
    src = root / "src" / "batch"
    return [
        ("add-rsa-2048-key", PRIYA, f"BILL-301: Generate an RSA key for invoice sealing\n\n{APPROVALS}",
         lambda: (src / "KEYGEN.cbl").write_text(KEYGEN)),
        ("add-sha-384-digest", JONAS, f"BILL-302: Add a SHA-384 digest of each invoice\n\n{APPROVALS}",
         lambda: (src / "INVHASH.cbl").write_text(DIGEST)),
        ("grow-rsa-key", PRIYA, f"BILL-303: Use a 3072-bit RSA key\n\n{APPROVALS}",
         lambda: edit(src / "KEYGEN.cbl", "VALUE 2048.", "VALUE 3072.")),
        ("one-approver-on-high", JONAS, f"BILL-304: Stop rounding the tax amount\n\n{ONE_APPROVAL}",
         lambda: edit(src / "TAXCALC.cbl", "COMPUTE LK-TAX ROUNDED =", "COMPUTE LK-TAX =")),
        ("unreadable-public-key-call", PRIYA, f"BILL-305: Encrypt the invoice key for the archive\n\n{APPROVALS}",
         lambda: edit(src / "KEYGEN.cbl", "000016     GOBACK.",
                      "000016     CALL 'CSNDPKE' USING WS-RC WS-REASON WS-KEY-TOKEN\n000017     GOBACK.")),
    ]


# PURPOSE: CREATES THE REPOSITORY AND RETURNS (NAME, SHA) FOR EACH SEEDED PULL REQUEST, AFTER THE IMPORT
def seed(root: Path) -> list[tuple[str, str]]:
    shutil.copytree(_impact.SYSTEM, root)
    config = root / "changeproof.yaml"
    config.write_text(config.read_text() + POLICY)
    run(root, "init", "-q", "-b", "main")
    commit(root, PRIYA, 1, f"BILL-300: Import the billing platform\n\n{APPROVALS}")
    shas = []
    for day, (name, author, message, apply) in enumerate(changes(root), 2):
        apply()
        shas.append((name, commit(root, author, day, message)))
    return shas
