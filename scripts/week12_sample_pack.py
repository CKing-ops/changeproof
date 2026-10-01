"""Builds the Week 12 sample evidence pack that is kept in the repository for review.

    uv run python scripts/week12_sample_pack.py

Seeds the synthetic billing repository from tests/fixtures/pack, makes fresh ML-DSA-87 and ECDSA
P-384 keys in a temporary folder, and writes the pack to docs/weekly/week12-pack with the two public
keys beside it. The private keys are thrown away, so this pack can never be re-signed. Needs OPA
and GnuCOBOL, like `changeproof pack`.
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
OUT = ROOT / "docs" / "weekly" / "week12-pack"
KEYS = ROOT / "docs" / "weekly" / "week12-pack-keys"
AT = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)  # RENAME: TIME STAMPED ON THE SAMPLE PACK


# PURPOSE: SEEDS THE REPOSITORY, SIGNS THE PACK WITH THROWAWAY KEYS, AND KEEPS THE PACK AND PUBLIC KEYS
def main() -> int:
    spec = importlib.util.spec_from_file_location("pack_seed", ROOT / "tests" / "fixtures" / "pack" / "seed.py")
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    shutil.rmtree(OUT, ignore_errors=True)
    shutil.rmtree(KEYS, ignore_errors=True)
    KEYS.mkdir(parents=True)
    with tempfile.TemporaryDirectory() as scratch:
        repo = Path(scratch) / "card-billing"
        shas = seed.seed(repo)
        keys = [generate_key(alg, Path(scratch) / alg) for alg in ("ml-dsa-87", "ecdsa-p384")]
        build_pack(repo, f"{shas['base']}..{shas['co-authored']}", OUT, [load_private(k.private_path) for k in keys],
                   release="card-billing v1.4 (synthetic)", at=AT, runner=LocalRunner())
        for k in keys:
            shutil.copy(k.public_path, KEYS / k.public_path.name)
    print(f"wrote {OUT.relative_to(ROOT)} and the public keys in {KEYS.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
