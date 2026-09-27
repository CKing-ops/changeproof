"""How far the tree-sitter approach carries to mainstream languages (universal-market check).

Samples: Apache Commons Lang 3.17.0 for Java (pinned in spike/build.sh), the Python standard
library, and the JavaScript in npm as shipped with Node. Nothing is committed from those trees;
only counts are recorded.
    uv run --group spike python spike/mainstream_spike.py
"""

import json
import sys
import time
from pathlib import Path

import tree_sitter
import tree_sitter_java
import tree_sitter_javascript
import tree_sitter_python

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "spike" / "results"
LIMIT = 3000  # RENAME: MAX FILES SAMPLED PER LANGUAGE

LANGUAGES = {  # RENAME: LANGUAGE NAME TO TREE-SITTER GRAMMAR MODULE
    "java": tree_sitter_java,
    "python": tree_sitter_python,
    "javascript": tree_sitter_javascript,
}


# PURPOSE: YIELDS (NAME, BYTES) FOR THE JAVA FILES IN THE PINNED COMMONS LANG CHECKOUT
def java_sources():
    base = ROOT / "spike" / "_build" / "commons-lang"
    for p in sorted(base.rglob("*.java"))[:LIMIT]:
        yield str(p.relative_to(base)), p.read_bytes()


# PURPOSE: YIELDS STDLIB PYTHON FILES, SKIPPING TEST DATA THAT IS BROKEN ON PURPOSE
def python_sources():
    base = Path(sys.base_prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}"
    files = sorted(p for p in base.rglob("*.py") if "test" not in p.parts and "site-packages" not in p.parts)
    for p in files[:LIMIT]:
        yield str(p.relative_to(base)), p.read_bytes()


# PURPOSE: YIELDS JAVASCRIPT FILES FROM THE NPM INSTALL THAT SHIPS WITH NODE
def javascript_sources():
    base = Path("/opt/node22/lib/node_modules/npm")
    for p in sorted(base.rglob("*.js"))[:LIMIT]:
        yield str(p.relative_to(base)), p.read_bytes()


SOURCES = {"java": java_sources, "python": python_sources, "javascript": javascript_sources}


# PURPOSE: PARSES EVERY SAMPLED FILE AND RETURNS CLEAN-PARSE RATE, LINES AND SPEED PER LANGUAGE
def measure(language: str) -> dict:
    parser = tree_sitter.Parser(tree_sitter.Language(LANGUAGES[language].language()))
    files = clean = lines = 0
    seconds = 0.0  # RENAME: TOTAL PARSE TIME FOR THE LANGUAGE
    for _, blob in SOURCES[language]():
        start = time.perf_counter()
        tree = parser.parse(blob)
        seconds += time.perf_counter() - start
        files += 1
        clean += not tree.root_node.has_error
        lines += blob.count(b"\n")
    return {"language": language, "files": files, "clean": clean, "rate": round(100 * clean / files, 1),
            "lines": lines, "seconds": round(seconds, 2), "lines_per_s": int(lines / seconds)}


# PURPOSE: RUNS ALL LANGUAGES AND WRITES THE SUMMARY TABLE
def main() -> int:
    rows = [measure(lang) for lang in LANGUAGES]
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "mainstream.json").write_text(json.dumps(rows, indent=2) + "\n")
    for row in rows:
        print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
