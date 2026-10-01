"""Builds the Week 11 Java repository: a synthetic payments service and six seeded changes.

The system is in `system/` beside this file and uses the `general` market profile. Each seeded change
is one commit; `expected.json` holds the impact a reviewer would mark for it, written by hand from
the code before the engine was run.
"""

import importlib.util
import shutil
from pathlib import Path

_spec = importlib.util.spec_from_file_location("change_seed", Path(__file__).resolve().parent.parent / "change" / "seed.py")
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
commit, edit, run = _helpers.commit, _helpers.edit, _helpers.run

SYSTEM = Path(__file__).resolve().parent / "system"
EXPECTED = Path(__file__).resolve().parent / "expected.json"
MEI = ("Mei Tanaka", "mei.tanaka@pay.example")
OLU = ("Olu Adeyemi", "olu.adeyemi@pay.example")
LEAD = "Sam Rivera <sam.rivera@pay.example>"
PKG = "src/main/java/com/example/pay"


# PURPOSE: EACH SEEDED CHANGE AS (NAME, AUTHOR, MESSAGE, EDIT TO APPLY TO THE WORK TREE)
def changes(root: Path) -> list:
    core, crypto, report = root / PKG / "core", root / PKG / "crypto", root / PKG / "report"
    return [
        ("fee-rate", MEI, "PAY-301: Raise the card fee to 1.75%",
         lambda: edit(core / "FeeCalculator.java", "RATE_BASIS_POINTS = 150;", "RATE_BASIS_POINTS = 175;")),
        ("ledger-absolute", OLU, "PAY-302: Post absolute amounts to the ledger",
         lambda: edit(core / "Ledger.java", "entries.add(amount);", "entries.add(Math.abs(amount));")),
        ("rsa-receipts", MEI, "PAY-303: Sign receipts with RSA for a legacy acquirer",
         lambda: (edit(crypto / "ReceiptSigner.java", 'KeyPairGenerator.getInstance("ML-DSA");',
                       'KeyPairGenerator.getInstance("RSA");\n        generator.initialize(2048);'),
                  edit(crypto / "ReceiptSigner.java", 'Signature.getInstance("ML-DSA");',
                       'Signature.getInstance("SHA256withRSA");'))),
        ("audit-header", OLU, "PAY-304: Version 2 of the audit export",
         lambda: edit(report / "AuditExport.java", '"PAYMENTS AUDIT V1"', '"PAYMENTS AUDIT V2"')),
        ("refund-cap", MEI, "PAY-305: Add a refund cap helper",
         lambda: edit(core / "FeeCalculator.java", "    public static long refundFee(long amount) {",
                      "    public static long maxRefund(long amount) {\n        return amount;\n    }\n\n"
                      "    public static long refundFee(long amount) {")),
        ("comment-only", OLU, "PAY-306: Explain the minimum fee",
         lambda: edit(core / "FeeCalculator.java", "    static final long MINIMUM_FEE = 25;",
                      "    // set by the card scheme agreement\n    static final long MINIMUM_FEE = 25;")),
    ]


# PURPOSE: CREATES THE REPOSITORY AND RETURNS (NAME, SHA) FOR EACH SEEDED CHANGE, AFTER THE IMPORT COMMIT
def seed(root: Path) -> list[tuple[str, str]]:
    shutil.copytree(SYSTEM, root)
    run(root, "init", "-q", "-b", "main")
    commit(root, MEI, 1, f"PAY-300: Import the payments service\n\nApproved-by: {LEAD}\nChange-Type: normal")
    shas = []
    for day, (name, author, subject, apply) in enumerate(changes(root), 2):
        apply()
        shas.append((name, commit(root, author, day, f"{subject}\n\nApproved-by: {LEAD}\nChange-Type: normal")))
    return shas
