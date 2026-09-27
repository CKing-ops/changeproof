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


# Implementor values for CCVS "X-card" placeholders (XXXXXnnn in columns 12-19). Values are ours;
# only their syntactic kind matters for parsing. Unlisted numbers become a quoted literal.
X_CARDS = {  # RENAME: X-CARD NUMBER TO SUBSTITUTED SOURCE TEXT
    **{n: f'"CPQUEUE{n}"' for n in range(30, 42)},
    42: '"CPTERM1"',
    43: '"CPTERM2"',
    47: '"."',
    48: '"copylib"',
    51: "SWITCH-1",
    52: "SWITCH-2",
    53: "MULTIPLE FILE TFIL",
    55: '"PRINTER"',
    56: "SYSOUT",
    57: "SYSIN",
    63: '" $$()*+,-./0123456789;<=>ABCDEFGHIJKLMNOPQRSTUVWXYZ"',
    64: '"ZYXWVUTSRQPONMLKJIHGFEDCBA>=<;9876543210/.-,+*)($$ "',
    65: "1000",
    67: "1000",
    68: "64000",
    69: "SYSIN",
    70: "STANDARD-1",
    73: "FORMFEED",
    74: "CPLABELID",
    81: '"12345678"',
    82: "CHANGEPROOF-HOST",
    83: "CHANGEPROOF-HOST",
    84: "STANDARD",
    86: "PIC X(8)",
    90: '"A"',
    91: '"D"',
}


# PURPOSE: APPLIES THE CCVS EXECUTIVE'S DEFAULT EXPANSION TO ONE SOURCE LINE
def expand_line(line: str) -> str:
    # With no *OPT cards selected, EXEC85 turns every optional line (a letter in column 7) into a comment.
    if len(line) > 6 and line[6].isalpha() and line[6] not in "Dd":
        line = line[:6] + "*" + line[7:]
    elif line[11:15] == "XXXX" and line[16:19].isdigit():
        number = int(line[16:19])  # RENAME: X-CARD NUMBER
        full_stop = "." if line[19:20] == "." else ""
        line = line[:11] + X_CARDS.get(number, f'"XXXXX{number:03}"') + full_stop
    return line


# PURPOSE: SPLITS NEWCOB.VAL ON *HEADER / *END-OF MARKERS AND WRITES EACH MEMBER
def split_members(text: str, out_dir: Path) -> dict[str, int]:
    counts = {folder: 0 for folder, _ in MEMBER_DIRS.values()}  # RENAME: FILES WRITTEN PER FOLDER
    current = None  # RENAME: (FOLDER, SUFFIX, MEMBER NAME, LINES) BEING COLLECTED
    for line in text.splitlines():
        if line.startswith("*HEADER,"):
            _, kind, name = line[:72].rstrip().split(",", 2)
            layout = MEMBER_DIRS.get(kind)
            current = (*layout, name.strip().replace(",", "_"), []) if layout else None
        elif line.startswith("*END-OF,"):
            if current:
                folder, suffix, name, lines = current
                if folder == "cobol":
                    lines = [expand_line(line) for line in lines]
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
