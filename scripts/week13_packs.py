"""Builds the three Week 13 evidence packs kept in the repository for the assessor review.

    uv run python scripts/week13_packs.py

The same synthetic billing release (tests/fixtures/pack) is packed three times: under the general
market and the hybrid profile, under eu-dora and hybrid, and under us-defense and CNSA 2.0, where
only ML-DSA-87 signs the attestations and an LMS key countersigns the pack statement. Keys are made
fresh in a temporary folder and only the public keys are kept, so these packs can never be re-signed.
Needs OPA and GnuCOBOL, like `changeproof pack`.
"""

import importlib.util
import shutil
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path

from changeproof.characterize import LocalRunner
from changeproof.pack import build_pack
from changeproof.signer import generate_key, load_private

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "weekly" / "week13-packs"
AT = datetime(2026, 10, 7, 12, 0, tzinfo=UTC)  # RENAME: TIME STAMPED ON THE THREE PACKS
SIGNING = {  # RENAME: PACK NAME TO THE ALGORITHMS THAT SIGN ITS ATTESTATIONS
    "general-hybrid": ("ml-dsa-87", "ecdsa-p384"),
    "eu-dora-hybrid": ("ml-dsa-87", "ecdsa-p384"),
    "us-defense-cnsa2": ("ml-dsa-87",),
}


# PURPOSE: SEEDS EACH SETUP, SIGNS ITS PACK WITH THROWAWAY KEYS, AND KEEPS THE PACKS AND PUBLIC KEYS
def main() -> int:
    spec = importlib.util.spec_from_file_location("pack_seed", ROOT / "tests" / "fixtures" / "pack" / "seed.py")
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    shutil.rmtree(OUT, ignore_errors=True)
    (OUT / "keys").mkdir(parents=True)
    with tempfile.TemporaryDirectory() as scratch:
        made = {alg: generate_key(alg, Path(scratch) / alg) for alg in ("ml-dsa-87", "ecdsa-p384", "lms-sha256-192")}
        for name, algs in SIGNING.items():
            repo = Path(scratch) / name / "card-billing"
            shas = seed.seed(repo, name)
            build_pack(repo, f"{shas['base']}..{shas['co-authored']}", OUT / name,
                       [load_private(made[a].private_path) for a in algs], release=f"card-billing v1.4 ({name}, synthetic)",
                       at=AT, runner=LocalRunner(), release_key=load_private(made["lms-sha256-192"].private_path))
        for key in made.values():
            shutil.copy(key.public_path, OUT / "keys" / key.public_path.name)
    print(f"wrote {len(SIGNING)} packs and their public keys in {OUT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
