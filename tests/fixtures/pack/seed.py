"""Builds the Week 12 repository: the synthetic batch programs under a config, then two changes to FEECALC.

`assisted` is the Week 9 refactor, made with an AI assistant named in an Assisted-by trailer and
approved by the team lead. `co-authored` raises the fee rate with an agent as co-author and no
approver at all, so the agent rule fails on it. `setup` picks one of the three Week 13 packs:
the same changes under the general, eu-dora or us-defense market, the last signed under CNSA 2.0.
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
ASSISTANT = "FeeBot Assistant 2.1 <feebot@tools.example>"
AGENT = "Claude <noreply@anthropic.com>"
CONFIG = """version: 0.1
market: {market}
system:
  name: card-billing
  owner: billing-engineering
  classification: {classification}
components:
  - id: batch-fees
    path: src/batch
    language: cobol
    criticality: high
    relied_on_by: [statement-print]
crypto:
{crypto}
policy:
  - rule: no-new-quantum-vulnerable-crypto
  - rule: agent-changes-need-independent-approval
  - rule: equivalence-required-outside-impact-set
"""
HYBRID = """  profile: hybrid
  signing: [ml-dsa-87, ecdsa-p384]
  release_signing: lms-sha256-192
  hash: sha-384"""
CNSA2 = """  profile: cnsa2
  signing: [ml-dsa-87]
  release_signing: lms-sha256-192
  hash: sha-384"""
SETUPS = {  # RENAME: PACK NAME TO (MARKET, CLASSIFICATION, CRYPTO SECTION); THE THREE WEEK 13 PACKS
    "general-hybrid": ("general", "confidential", HYBRID),
    "eu-dora-hybrid": ("eu-dora", "confidential", HYBRID),
    "us-defense-cnsa2": ("us-defense", "unclassified", CNSA2),
}


# PURPOSE: CREATES THE REPOSITORY; RETURNS EACH CHANGE'S NAME WITH ITS COMMIT
def seed(root: Path, setup: str = "general-hybrid") -> dict[str, str]:
    src = root / "src" / "batch"
    src.mkdir(parents=True)
    for program in sorted(BATCH.glob("*.cbl")):
        shutil.copy(program, src / program.name)
    market, classification, crypto = SETUPS[setup]
    (root / "changeproof.yaml").write_text(CONFIG.format(market=market, classification=classification, crypto=crypto))
    run(root, "init", "-q", "-b", "main")
    shas = {"base": commit(root, AUTHOR, 1, f"LOAN-1: Import batch programs\n\nApproved-by: {LEAD}")}
    edit(src / "FEECALC.cbl", "ADD 40 TO LK-FEE", "COMPUTE LK-FEE = LK-FEE + 40")
    shas["assisted"] = commit(root, AUTHOR, 2, "LOAN-2: Write the late fee as a COMPUTE\n\n"
                                               f"Assisted-by: {ASSISTANT}\nApproved-by: {LEAD}")
    edit(src / "FEECALC.cbl", "LK-AMOUNT * 0.015", "LK-AMOUNT * 0.0175")
    shas["co-authored"] = commit(root, AUTHOR, 3, f"LOAN-3: Raise the personal fee rate\n\nCo-authored-by: {AGENT}")
    return shas
