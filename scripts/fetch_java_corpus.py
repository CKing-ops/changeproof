"""Fetch the pinned Apache Commons Lang history used by the Week 11 Java exit check.

    uv run python scripts/fetch_java_corpus.py

Setup-time only; the engine itself never opens a network connection. Apache-2.0 code, kept out of
the repository (corpus/java/ is ignored) and fetched by commit, so git checks every object against
the pinned hash.
"""

import subprocess
import sys
from pathlib import Path

REPO = "https://github.com/apache/commons-lang.git"
COMMIT = "29ccc7665f3bc5d84155a3092ab2209a053324e6"  # RENAME: PINNED HEAD, COMMITTED 2024-08-24
DEPTH = 41  # RENAME: COMMITS OF HISTORY FETCHED; THE OLDEST ONLY SERVES AS A PARENT
OUT = Path(__file__).resolve().parent.parent / "corpus" / "java" / "commons-lang"


# PURPOSE: RUNS GIT IN THE CHECKOUT
def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(OUT), *args], check=True, capture_output=True, text=True).stdout.strip()


# PURPOSE: FETCHES THE PINNED COMMIT WITH ITS RECENT HISTORY AND CHECKS IT OUT
def main() -> int:
    if not (OUT / ".git").is_dir():
        OUT.mkdir(parents=True, exist_ok=True)
        git("init", "-q")
    git("fetch", "-q", f"--depth={DEPTH}", REPO, COMMIT)
    git("checkout", "-q", "--detach", COMMIT)
    head = git("rev-parse", "HEAD")
    if head != COMMIT:
        print(f"checked out {head}, pinned {COMMIT}", file=sys.stderr)
        return 1
    print(f"{OUT} at {head}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
