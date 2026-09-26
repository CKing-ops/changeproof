"""Fetch the pinned NIST CCVS85 suite and split it into one file per program.

Setup-time only. The engine itself never opens a network connection.
"""

import hashlib
import io
import sys
import tarfile
import urllib.request
from pathlib import Path

NIST_URL = "https://sourceforge.net/projects/gnucobol/files/nist/newcob.val.tar.gz/download"
NIST_SHA256 = "e4513f26a9b38911f7bf882fe3d3339a80b45cabc2caf85eb3055b0f5ce87ee0"
MEMBER_DIRS = {"COBOL": ("cobol", ".CBL"), "CLBRY": ("clbry", ".CPY")}  # RENAME: CCVS SECTION TYPE TO FOLDER AND SUFFIX

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "corpus" / "nist"


# PURPOSE: DOWNLOADS THE ARCHIVE AND REFUSES IT UNLESS THE HASH MATCHES THE PIN
def download(url: str, sha256: str) -> bytes:
    with urllib.request.urlopen(url, timeout=120) as resp:
        blob = resp.read()
    digest = hashlib.sha256(blob).hexdigest()
    if digest != sha256:
        raise SystemExit(f"hash mismatch for {url}: got {digest}, pinned {sha256}")
    return blob


# PURPOSE: PULLS THE NEWCOB.VAL TEXT OUT OF THE GZIPPED TARBALL
def extract_newcob(blob: bytes) -> str:
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tar:
        member = tar.extractfile("newcob.val")
        return member.read().decode("latin-1")


# PURPOSE: KEEPS CCVS OPTIONAL-FEATURE LINES BY BLANKING THEIR COLUMN-7 SELECTOR LETTER
def enable_optional_line(line: str) -> str:
    # EXEC85 normally decides per letter; for parse testing every optional line is kept.
    if len(line) > 6 and line[6].isalpha() and line[6] not in "Dd":
        return line[:6] + " " + line[7:]
    return line


# PURPOSE: SPLITS NEWCOB.VAL ON *HEADER / *END-OF MARKERS AND WRITES EACH MEMBER
def split_members(text: str, out_dir: Path) -> dict[str, int]:
    counts = {folder: 0 for folder, _ in MEMBER_DIRS.values()}  # RENAME: FILES WRITTEN PER FOLDER
    current = None  # RENAME: (FOLDER, SUFFIX, MEMBER NAME, LINES) BEING COLLECTED
    for line in text.splitlines():
        if line.startswith("*HEADER,"):
            _, kind, name = line[:72].rstrip().split(",", 2)
            layout = MEMBER_DIRS.get(kind)
            current = (*layout, name.strip(), []) if layout else None
        elif line.startswith("*END-OF,"):
            if current:
                folder, suffix, name, lines = current
                if folder == "cobol":
                    lines = [enable_optional_line(line) for line in lines]
                target = out_dir / folder / f"{name}{suffix}"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text("\n".join(lines) + "\n", encoding="latin-1")
                counts[folder] += 1
            current = None
        elif current:
            current[3].append(line)
    return counts


# PURPOSE: FETCHES, VERIFIES AND SPLITS THE NIST SUITE INTO CORPUS/NIST
def main() -> int:
    blob = download(NIST_URL, NIST_SHA256)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    counts = split_members(extract_newcob(blob), OUT_DIR)
    (OUT_DIR / "SOURCE.txt").write_text(f"{NIST_URL}\nsha256 {NIST_SHA256}\n")
    print(", ".join(f"{k}: {v}" for k, v in counts.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
