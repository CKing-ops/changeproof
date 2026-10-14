"""Merge commits as GitLab writes them: the person who presses merge authors the merge commit, the
branch's commits carry the real authors, and the trailers name approvers, reviewers and the merger.

`human` merges Priya's fee-rate change: Dana merges and approves it, and an AI reviewer is named in a
Reviewed-by trailer. `bot` merges a dependency bot's change that Lena also pushed to: Lena and Dana
approve it, so one approver is independent. The shapes follow GitLab Runner's history (MIT); names,
addresses and code are synthetic.
"""

import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location("pack_seed", Path(__file__).resolve().parent.parent / "pack" / "seed.py")
_pack = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_pack)
commit, edit, run = _pack.commit, _pack.edit, _pack.run

PRIYA = ("Priya Raman", "priya.raman@billing.example")
DANA = ("Dana Okafor", "dana.okafor@billing.example")
LENA = ("Lena Vogel", "lena.vogel@billing.example")
BOT = ("Billing Renovate Bot", "billing-bot@deps.example")
DUO = "GitLab Duo <gitlab-duo@gitlab.com>"


# PURPOSE: MERGES A BRANCH WITH A MERGE COMMIT AUTHORED BY THE MERGER, AS A CODE HOST DOES
def merge(root: Path, branch: str, merger: tuple[str, str], day: int, message: str) -> str:
    when = f"2026-09-{day:02d}T09:30:00+02:00"
    run(root, "merge", "-q", "--no-ff", branch, "-m", message, env={
        "GIT_AUTHOR_NAME": merger[0], "GIT_AUTHOR_EMAIL": merger[1], "GIT_AUTHOR_DATE": when,
        "GIT_COMMITTER_NAME": merger[0], "GIT_COMMITTER_EMAIL": merger[1], "GIT_COMMITTER_DATE": when,
    })
    return run(root, "rev-parse", "HEAD")


# PURPOSE: CREATES THE REPOSITORY; RETURNS EACH COMMIT'S NAME WITH ITS SHA
def seed(root: Path) -> dict[str, str]:
    shas = {"base": _pack.seed(root)["co-authored"]}
    src = root / "src" / "batch"
    run(root, "checkout", "-q", "-b", "fee")
    edit(src / "FEECALC.cbl", "LK-AMOUNT * 0.0175", "LK-AMOUNT * 0.018")
    shas["fee"] = commit(root, PRIYA, 4, "LOAN-4: Raise the personal fee rate to 1.8%")
    run(root, "checkout", "-q", "main")
    shas["human"] = merge(root, "fee", DANA, 5, "Merge branch 'fee' into 'main'\n\nLOAN-4: Raise the personal fee rate "
                          "to 1.8%\n\nSee merge request billing/card-billing!12\n\n"
                          f"Merged-by: {DANA[0]} <{DANA[1]}>\nApproved-by: {DANA[0]} <{DANA[1]}>\nReviewed-by: {DUO}")
    run(root, "checkout", "-q", "-b", "deps")
    (root / "deps.txt").write_text("copybook-tools 2.4.1\n")
    shas["bump"] = commit(root, BOT, 6, "Update copybook-tools to 2.4.1")
    (root / "deps.txt").write_text("copybook-tools 2.4.2\n")
    shas["fixup"] = commit(root, LENA, 7, "Pin copybook-tools 2.4.2")
    run(root, "checkout", "-q", "main")
    shas["bot"] = merge(root, "deps", DANA, 8, "Merge branch 'deps' into 'main'\n\nLOAN-5: Update copybook-tools\n\n"
                        f"Merged-by: {DANA[0]} <{DANA[1]}>\nApproved-by: {LENA[0]} <{LENA[1]}>\n"
                        f"Approved-by: {DANA[0]} <{DANA[1]}>")
    return shas
