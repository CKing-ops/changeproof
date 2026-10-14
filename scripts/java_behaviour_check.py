"""Runs the Java behaviour check on the pinned Apache Commons Lang history and on planted bugs.

    uv run python scripts/fetch_java_corpus.py
    uv run python scripts/java_behaviour_check.py

For each of the latest commits that touch main Java code, the probe cases of the changed files are built
at the parent, then run at the parent and at the commit. Release-prep and refactoring commits should
come out all `same`. Then three bugs are planted in a copy of the pinned head and must come out
`different`. Writes docs/weekly/java-behaviour-commons-lang.json. Needs a JDK; no network.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from changeproof.characterize import java

ROOT = Path(__file__).resolve().parent.parent
REPO = ROOT / "corpus" / "java" / "commons-lang"
OUT = ROOT / "docs" / "weekly" / "java-behaviour-commons-lang.json"
COMMITS = 12  # RENAME: LATEST COMMITS TOUCHING MAIN JAVA CODE THAT ARE CHECKED
MAIN = "src/main/java"
LANG = f"{MAIN}/org/apache/commons/lang3"
PLANTED = [  # RENAME: BUGS PLANTED IN THE PINNED HEAD: FILE, TEXT, REPLACEMENT
    (f"{LANG}/StringUtils.java", "return cs == null || cs.length() == 0;", "return cs == null || cs.length() <= 1;"),
    (f"{LANG}/StringUtils.java", "if (firstCodepoint == newCodePoint) {", "if (firstCodepoint != newCodePoint) {"),
    (f"{LANG}/BooleanUtils.java", "return toBooleanObject(str) == Boolean.TRUE;",
     "return toBooleanObject(str) != Boolean.FALSE;"),
]


# PURPOSE: RUNS GIT IN THE CORPUS CHECKOUT
def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), *args], check=True, capture_output=True, text=True).stdout


# PURPOSE: WRITES THE TREE OF A REVISION INTO A NEW FOLDER
def tree(rev: str, folder: Path) -> Path:
    folder.mkdir(parents=True)
    archive = subprocess.run(["git", "-C", str(REPO), "archive", rev], check=True, capture_output=True).stdout
    subprocess.run(["tar", "-x", "-C", str(folder)], input=archive, check=True)
    return folder


# PURPOSE: COMPARES TWO TREES ON THE GIVEN FILES AND SUMS UP THE RESULT
def check(before: Path, after: Path, scope: set[str], scratch: Path) -> dict:
    tests, untested = java.compare(before, after, lambda path: path in scope, scratch)
    different = sorted({t["id"].rpartition("#")[0] for t in tests if t["result"] != "same"})
    return {"files": sorted(scope), "cases": len(tests), "different": sum(t["result"] != "same" for t in tests),
            "methods_different": different,
            "untested": [{"program": u.get("program"), "reason": u["reason"]} for u in untested]}


# PURPOSE: CHECKS THE LATEST COMMITS AND THE PLANTED BUGS, AND KEEPS THE RESULTS
def main() -> int:
    if java.JDK is None or not (REPO / ".git").is_dir():
        print("needs a JDK and the corpus from scripts/fetch_java_corpus.py", file=sys.stderr)
        return 1
    head = git("rev-parse", "HEAD").strip()
    found = {"corpus": "apache/commons-lang", "head": head, "jdk": java.describe(), "commits": [], "planted": []}
    for rev in git("log", "--format=%H", f"-{COMMITS}", "--", MAIN).split():
        scope = {p for p in git("diff", "--name-only", f"{rev}~1", rev, "--", MAIN).split() if p.endswith(".java")}
        with tempfile.TemporaryDirectory() as scratch:
            work = Path(scratch)
            result = check(tree(f"{rev}~1", work / "base"), tree(rev, work / "head"), scope, work / "run")
        found["commits"].append({"commit": rev, "subject": git("log", "-1", "--format=%s", rev).strip()} | result)
        print(f"{rev[:12]}: {result['cases']} cases, {result['different']} different", flush=True)
    for path, old, new in PLANTED:
        with tempfile.TemporaryDirectory() as scratch:
            work = Path(scratch)
            base, mutant = tree(head, work / "base"), tree(head, work / "head")
            text = (mutant / path).read_text(encoding="utf-8")
            if old not in text:
                print(f"{path}: planted text not found", file=sys.stderr)
                return 1
            (mutant / path).write_text(text.replace(old, new, 1), encoding="utf-8")
            result = check(base, mutant, {path}, work / "run")
        found["planted"].append({"file": path, "from": old, "to": new} | result)
        print(f"planted in {path}: {result['different']} different {result['methods_different']}", flush=True)
    OUT.write_text(json.dumps(found, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
