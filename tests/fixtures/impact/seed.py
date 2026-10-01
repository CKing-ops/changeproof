"""Builds the Week 5 exit-check repository: a synthetic billing platform and eleven seeded changes.

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
PRIYA = ("Priya Raman", "priya.raman@billing.example")
JONAS = ("Jonas Berg", "jonas.berg@billing.example")
LEAD = "Dana Okafor <dana.okafor@billing.example>"


# PURPOSE: EACH SEEDED CHANGE AS (NAME, AUTHOR, MESSAGE, EDIT TO APPLY TO THE WORK TREE)
def changes(root: Path) -> list:
    src = root / "src" / "batch"
    return [
        ("tax-rounding", PRIYA, "BILL-201: Stop rounding the tax amount",
         lambda: edit(src / "TAXCALC.cbl", "COMPUTE LK-TAX ROUNDED =", "COMPUTE LK-TAX =")),
        ("customer-tier-field", JONAS, "BILL-202: Add the customer tier to the customer record",
         lambda: edit(root / "copy/CUSTREC.cpy", "000004     05  CUST-STATUS         PIC X(8).\n",
                      "000004     05  CUST-STATUS         PIC X(8).\n000005     05  CUST-TIER           PIC X(2).\n")),
        ("hmac-instead-of-signature", PRIYA, "BILL-203: Seal invoices with an HMAC instead of a signature",
         lambda: edit(src / "INVSIGN.cbl", "CALL 'CSNDDSG'", "CALL 'CSNBHMG'")),
        ("report-reads-v2-file", JONAS, "BILL-204: Point the invoice report at the version 2 file",
         lambda: edit(root / "jcl/INVJOB.jcl", "//INVIN    DD DSN=BILL.INV.OUT,", "//INVIN    DD DSN=BILL.INV.OUT.V2,")),
        ("report-open-invoices-only", JONAS, "BILL-205: Report open invoices only",
         lambda: edit(src / "INVRPT.cbl", "FROM INVOICES\n", "FROM INVOICES\n000022         WHERE STATUS = 'O'\n")),
        ("audit-stamp-text", PRIYA, "BILL-206: Name the batch in the audit stamp",
         lambda: edit(src / "AUDLOG.cbl", "'NIGHTLY RUN'", "'NIGHTLY BATCH'")),
        ("discount-paragraph", PRIYA, "BILL-207: Apply the early-payment discount",
         lambda: (edit(src / "INVMAIN.cbl", "000025     PERFORM PRICE-PARA\n",
                       "000025     PERFORM PRICE-PARA\n000025     PERFORM DISC-PARA\n"),
                  edit(src / "INVMAIN.cbl", "000033 SIGN-PARA.",
                       "000033 DISC-PARA.\n000033     COMPUTE WS-TOTAL = WS-TOTAL * 0.98.\n000033 SIGN-PARA."))),
        ("retire-signing-program", JONAS, "BILL-208: Retire the invoice signing program",
         lambda: (src / "INVSIGN.cbl").unlink()),
        ("customer-status-value", JONAS, "BILL-209: Mark updated customers as open",
         lambda: edit(root / "src/online/CUSTUPD.cbl", "'ACTIVE'", "'OPEN'")),
        ("tax-rate-value", PRIYA, "BILL-210: Raise the tax rate to 21 percent",
         lambda: edit(root / "copy/TAXRATE.cpy", "VALUE .2000.", "VALUE .2100.")),
        ("move-report-program", JONAS, "BILL-211: Move the invoice report under src/reports",
         lambda: ((root / "src/reports").mkdir(), run(root, "mv", "src/batch/INVRPT.cbl", "src/reports/INVRPT.cbl"))),
    ]


# PURPOSE: CREATES THE REPOSITORY AND RETURNS (NAME, SHA) FOR EACH SEEDED CHANGE, AFTER THE IMPORT COMMIT
def seed(root: Path) -> list[tuple[str, str]]:
    shutil.copytree(SYSTEM, root)
    run(root, "init", "-q", "-b", "main")
    commit(root, PRIYA, 1, f"BILL-200: Import the billing platform\n\nApproved-by: {LEAD}\nChange-Type: normal")
    shas = []
    for day, (name, author, subject, apply) in enumerate(changes(root), 2):
        apply()
        shas.append((name, commit(root, author, day, f"{subject}\n\nApproved-by: {LEAD}\nChange-Type: normal")))
    return shas
