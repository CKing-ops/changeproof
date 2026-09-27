"""Builds the Week 4 exit-check repository: ten commits to a synthetic SEPA batch system.

Each commit exercises one kind of change: a new system, a field-level edit, a copybook change, a new
paragraph, a move, a JCL change, a removal, a comment-only edit, an emergency fix approved by its own
implementer, and a change with no ticket at all.
"""

import os
import shutil
import subprocess
from pathlib import Path

FIXTURES = Path(__file__).resolve().parent.parent / "graph"
ANA = ("Ana Novak", "ana.novak@bank.example")
TOMAS = ("Tomas Horvat", "tomas.horvat@bank.example")
LENA = "Lena Weber <lena.weber@bank.example>"
MARC = "Marc Dubois <marc.dubois@bank.example>"
BOT = ("Release Bot", "release-bot@bank.example")


# PURPOSE: RUNS GIT IN THE SEED REPOSITORY WITH NO USER OR SYSTEM CONFIG
def run(root: Path, *args: str, env: dict | None = None) -> str:
    base = {"PATH": os.environ["PATH"], "HOME": str(root), "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1", "TZ": "UTC"}
    return subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, text=True,
                          env=base | (env or {})).stdout.strip()


# PURPOSE: COMMITS EVERYTHING IN THE WORK TREE AS THE GIVEN AUTHOR, AT A FIXED TIME
def commit(root: Path, author: tuple[str, str], day: int, message: str, committer: tuple[str, str] | None = None) -> str:
    committer = committer or author
    when = f"2026-09-{day:02d}T09:30:00+02:00"
    run(root, "add", "-A")
    run(root, "commit", "-q", "-m", message, env={
        "GIT_AUTHOR_NAME": author[0], "GIT_AUTHOR_EMAIL": author[1], "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_NAME": committer[0], "GIT_COMMITTER_EMAIL": committer[1], "GIT_COMMITTER_DATE": when,
    })
    return run(root, "rev-parse", "HEAD")


# PURPOSE: REPLACES ONE EXACT PIECE OF TEXT IN A FILE, FAILING IF IT IS NOT THERE
def edit(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    assert old in text, (path, old)
    path.write_text(text.replace(old, new, 1))


# PURPOSE: CREATES THE REPOSITORY AND RETURNS THE TEN COMMIT SHAS IN ORDER
def seed(root: Path) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    run(root, "init", "-q", "-b", "main")
    for rel in ("src/BATCH1.cbl", "src/SUBPGM.cbl", "src/FLOWS.cbl", "copy/ACCTWS.cpy", "jcl/RUNBATCH.jcl",
                "changeproof.yaml"):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIXTURES / rel, root / rel)
    shas = [commit(root, ANA, 1, "Import the SEPA batch programs\n\n"
                   f"Change-Request: CHG0030001\nRequested-by: {LENA}\nApproved-by: {MARC}\nChange-Type: normal")]

    edit(root / "src/FLOWS.cbl", "COMPUTE WS-FEE OF WS-TXN =", "COMPUTE WS-FEE OF WS-TXN ROUNDED =")
    shas.append(commit(root, ANA, 2, "PAY-101: Round the SEPA fee before netting\n\n"
                       "The fee was truncated, so the net amount could be off by a cent.\n\n"
                       f"Requested-by: {LENA}\nApproved-by: {MARC}\nChange-Type: normal"))

    edit(root / "copy/ACCTWS.cpy", "000005 01  WS-BAL", "000005 01  WS-LIMIT                PIC S9(9)V99 COMP-3.\n"
         "000006 01  WS-BAL")
    shas.append(commit(root, TOMAS, 3, "Add the overdraft limit to the account layout\n\n"
                       f"Change-Request: CHG0030002\nRequested-by: {LENA}\nApproved-by: {MARC}\n"
                       "Change-Type: normal", committer=BOT))

    edit(root / "src/BATCH1.cbl", "000039     PERFORM MISSING-PARA.",
         "000039     PERFORM MISSING-PARA\n000039     PERFORM AUDIT-PARA.")
    edit(root / "src/BATCH1.cbl", "000042     STOP RUN.", "000042     STOP RUN.\n000043 AUDIT-PARA.\n"
         "000044     ADD 1 TO WS-COUNT.")
    shas.append(commit(root, TOMAS, 4, "[PAY-102] Count each account read for the audit total\n\n"
                       f"Requested-by: {LENA}\nApproved-by: Ana Novak <ana.novak@bank.example>\nChange-Type: normal"))

    (root / "src/online").mkdir()
    run(root, "mv", "src/SUBPGM.cbl", "src/online/SUBPGM.cbl")
    shas.append(commit(root, TOMAS, 5, "Move the account lookup under src/online\n\n"
                       f"Refs: CHG0030003\nApproved-by: {MARC}\nChange-Type: standard"))

    edit(root / "jcl/RUNBATCH.jcl", "DSN=TEST.ACCT.DATA,", "DSN=TEST.ACCT.DATA.V2,")
    shas.append(commit(root, ANA, 6, "Point the nightly run at the version 2 account file\n\n"
                       f"Change-Request: CHG0030004\nRequested-by: {LENA}\nApproved-by: {MARC}\nChange-Type: normal"))

    edit(root / "src/BATCH1.cbl", "000039     PERFORM MISSING-PARA\n000039     PERFORM AUDIT-PARA.",
         "000039     PERFORM MISSING-PARA.")
    edit(root / "src/BATCH1.cbl", "\n000043 AUDIT-PARA.\n000044     ADD 1 TO WS-COUNT.", "")
    shas.append(commit(root, TOMAS, 7, "Drop the audit count again\n\n"
                       "Operations asked for it to be removed until the report exists (ISO-27001 review).\n\n"
                       f"Refs: PAY-102\nRequested-by: {LENA}\nApproved-by: {MARC}\nChange-Type: normal"))

    edit(root / "src/FLOWS.cbl", "000022 01  WS-RATE", "000022*RATE AGREED WITH THE SCHEME, SEE FEE SCHEDULE 2026\n"
         "000022 01  WS-RATE")
    shas.append(commit(root, ANA, 8, "Document where the fee rate comes from\n\nRefs: CHG0030005\nChange-Type: standard"))

    edit(root / "src/FLOWS.cbl", "000030     ADD WS-AMOUNT OF WS-TXN TO WS-AMOUNT OF WS-TOTALS",
         "000030     IF WS-AMOUNT OF WS-TXN NOT = ZERO\n"
         "000030         ADD WS-AMOUNT OF WS-TXN TO WS-AMOUNT OF WS-TOTALS\n000030     END-IF")
    shas.append(commit(root, ANA, 9, "Skip zero-amount transactions in the totals\n\n"
                       "Zero-amount SEPA returns were counted twice, see INC0045678.\n\n"
                       "Approved-by: Ana Novak <ana.novak@bank.example>\nChange-Type: emergency"))

    edit(root / "src/online/SUBPGM.cbl", "CALL 'CSNBOWH'", "CALL 'CSNBHMG'")
    (root / "README.md").write_text("SEPA batch programs used by the changeproof Week 4 exit check.\n")
    shas.append(commit(root, TOMAS, 10, "Switch the lookup hash to HMAC and add a readme"))
    return shas
