"""Week 1 parser spike: tree-sitter-cobol vs the ANTLR4 Cobol85 grammar (Python target).

Run spike/build.sh and scripts/fetch_corpus.py first, then:
    uv run --group spike python spike/parser_spike.py

A file "parses" when the parser reports no syntax errors. Copybooks are not inlined for either
candidate, so both see exactly the same text.
"""

import ctypes
import json
import re
import signal
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD = ROOT / "spike" / "_build"
RESULTS = ROOT / "spike" / "results"
TIMEOUT_S = 120  # RENAME: PER-FILE PARSE BUDGET IN SECONDS

CORPORA = {  # RENAME: CORPUS NAME TO PROGRAM GLOB
    "carddemo": (ROOT / "corpus" / "carddemo", "**/*.[cC][bB][lL]"),
    "nist": (ROOT / "corpus" / "nist" / "cobol", "*.CBL"),
}


# PURPOSE: LOADS THE COMPILED TREE-SITTER-COBOL LIBRARY AS A PARSER
def tree_sitter_parser():
    import tree_sitter

    lib = ctypes.CDLL(str(BUILD / "tree-sitter-cobol.so"))
    lib.tree_sitter_COBOL.restype = ctypes.c_void_p
    new_capsule = ctypes.pythonapi.PyCapsule_New
    new_capsule.restype = ctypes.py_object
    new_capsule.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_void_p]
    capsule = new_capsule(lib.tree_sitter_COBOL(), b"tree_sitter.Language", None)
    return tree_sitter.Parser(tree_sitter.Language(capsule))


# PURPOSE: PARSES ONE FILE WITH TREE-SITTER AND RETURNS ERROR COUNT AND FIRST ERROR LINE
def parse_tree_sitter(path: str) -> dict:
    parser = tree_sitter_parser()
    text = Path(path).read_text(encoding="latin-1")
    tree = parser.parse(mask_exec_blocks(text).encode("latin-1"))
    errors = []  # RENAME: 1-BASED LINES OF ERROR OR MISSING NODES
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if node.is_error or node.is_missing:
            errors.append(node.start_point[0] + 1)
        elif node.has_error:
            stack.extend(node.children)
    return {"errors": len(errors), "first_error_line": min(errors, default=None)}


EXEC_RE = re.compile(r"\bEXEC\s+(SQL|CICS|DLI)\b(.*?)\bEND-EXEC\b", re.IGNORECASE | re.DOTALL)
COPY_RE = re.compile(r"\bCOPY\s+[\w-]+(?:\s+(?:OF|IN)\s+[\w-]+)?(?:\s+REPLACING\b.*?)?\s*\.", re.IGNORECASE | re.DOTALL)
PROCESS_RE = re.compile(r"^\s*(CBL|PROCESS)\b", re.IGNORECASE)


COMMENT_ENTRY_RE = re.compile(
    r"^(\s*(?:AUTHOR|INSTALLATION|DATE-WRITTEN|DATE-COMPILED|SECURITY|REMARKS)\s*\.)(.*)$", re.IGNORECASE
)
DIVISION_RE = re.compile(r"^\s*[\w-]+\s+DIVISION\b", re.IGNORECASE)
ID_DIVISION_RE = re.compile(r"^\s*(IDENTIFICATION|ID)\s+DIVISION\b", re.IGNORECASE)
ID_PARAGRAPH_RE = re.compile(r"^\s*(PROGRAM-ID|AUTHOR|INSTALLATION|DATE-WRITTEN|DATE-COMPILED|SECURITY|REMARKS)\s*\.", re.IGNORECASE)


# PURPOSE: BLANKS EXEC ... END-EXEC IN COLUMNS 8-72, LEAVING CONTINUE IN THE PROCEDURE DIVISION
def mask_exec_blocks(text: str) -> str:
    lines = text.splitlines()
    areas = [  # RENAME: CODE AREA (COLUMNS 8-72) PER LINE, EMPTY FOR COMMENT LINES
        "" if len(line) > 6 and line[6] in "*/" else line[7:72].ljust(65) for line in lines
    ]
    joined = "\n".join(areas)
    proc_start = re.search(r"\bPROCEDURE\s+DIVISION\b", joined, re.IGNORECASE)
    chars = list(joined)
    for m in EXEC_RE.finditer(joined):
        for i in range(m.start(), m.end()):
            if chars[i] != "\n":
                chars[i] = " "
        if proc_start and m.start() > proc_start.start():
            chars[m.start():m.start() + 8] = "CONTINUE"
    masked = "".join(chars).split("\n")
    return "\n".join(
        line if not areas[i] else line[:7].ljust(7) + masked[i] + line[72:]
        for i, line in enumerate(lines)
    ) + "\n"


# PURPOSE: TURNS FIXED-FORMAT SOURCE INTO FREE TEXT WITH THE SAME LINE COUNT
def normalize_fixed_format(text: str) -> list[str]:
    out = []  # RENAME: NORMALIZED LINES, ONE PER SOURCE LINE
    for raw in text.splitlines():
        line = raw.ljust(72)
        indicator, area = line[6], line[7:72]
        if indicator in "*/dD" or PROCESS_RE.match(line[:72]):
            out.append("")
        elif indicator == "-" and out:
            quote = re.search(r"['\"]", area)
            prev = len(out) - 1
            while prev > 0 and not out[prev]:
                prev -= 1
            tail = area[quote.end():] if quote else area.lstrip()
            out[prev] = out[prev] + tail.rstrip() if quote else out[prev].rstrip() + " " + tail.rstrip()
            out.append("")
        else:
            out.append(" " + area.rstrip())
    return tag_comment_entries(out)


# PURPOSE: MARKS IDENTIFICATION-DIVISION COMMENT ENTRIES (AUTHOR. ETC.) WITH THE *>CE TAG
def tag_comment_entries(lines: list[str]) -> list[str]:
    in_entry = False  # RENAME: INSIDE A FREE-TEXT COMMENT-ENTRY PARAGRAPH
    for i, line in enumerate(lines):
        if DIVISION_RE.match(line) and not ID_DIVISION_RE.match(line):
            break
        if m := COMMENT_ENTRY_RE.match(line):
            in_entry = True
            lines[i] = m.group(1) + (f" *>CE {m.group(2).strip()}" if m.group(2).strip() else "")
        elif ID_PARAGRAPH_RE.match(line):
            in_entry = False
        elif in_entry and line.strip():
            lines[i] = f" *>CE {line.strip()}"
    return lines


# PURPOSE: MIMICS THE PROLEAP PREPROCESSOR ENOUGH FOR THE ANTLR GRAMMAR TO ACCEPT EXEC AND COPY
def preprocess_for_antlr(text: str) -> str:
    body = "\n".join(normalize_fixed_format(text))
    body = COPY_RE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), body)

    # PURPOSE: PREFIXES EACH LINE OF AN EXEC BLOCK WITH THE GRAMMAR'S TAG
    def tag_exec(m: re.Match) -> str:
        tag = "*>EXECCICS" if m.group(1).upper() == "CICS" else "*>EXECSQL"
        tagged = [f"{tag} {part.strip()}" for part in m.group(0).split("\n")]
        tagged[-1] += "}"
        return "\n".join(tagged)

    return EXEC_RE.sub(tag_exec, body) + "\n"


# PURPOSE: PARSES ONE FILE WITH THE GENERATED ANTLR PARSER AND COUNTS SYNTAX ERRORS
def parse_antlr(path: str) -> dict:
    sys.path.insert(0, str(BUILD / "antlr"))
    from antlr4 import CommonTokenStream, InputStream
    from antlr4.error.ErrorListener import ErrorListener
    from Cobol85Lexer import Cobol85Lexer
    from Cobol85Parser import Cobol85Parser

    class Collect(ErrorListener):
        # PURPOSE: STARTS AN EMPTY ERROR-LINE LIST
        def __init__(self):
            self.lines = []  # RENAME: LINES WHERE ANTLR REPORTED A SYNTAX ERROR

        # PURPOSE: RECORDS THE LINE OF EACH SYNTAX ERROR ANTLR REPORTS
        def syntaxError(self, recognizer, offending, line, column, msg, e):
            self.lines.append(line)

    text = preprocess_for_antlr(Path(path).read_text(encoding="latin-1"))
    collect = Collect()
    lexer = Cobol85Lexer(InputStream(text))
    lexer.removeErrorListeners()
    lexer.addErrorListener(collect)
    parser = Cobol85Parser(CommonTokenStream(lexer))
    parser.removeErrorListeners()
    parser.addErrorListener(collect)
    parser.startRule()
    return {"errors": len(collect.lines), "first_error_line": min(collect.lines, default=None)}


CANDIDATES = {"tree-sitter-cobol": parse_tree_sitter, "antlr4-cobol85": parse_antlr}


# PURPOSE: TURNS SIGALRM INTO AN EXCEPTION SO A SLOW FILE FAILS WITHOUT KILLING THE WORKER
def raise_timeout(signum, frame):
    raise TimeoutError(f"parse exceeded {TIMEOUT_S}s")


# PURPOSE: RUNS ONE CANDIDATE ON ONE FILE AND TIMES IT
def run_one(candidate: str, path: str) -> dict:
    signal.signal(signal.SIGALRM, raise_timeout)
    signal.alarm(TIMEOUT_S)
    start = time.perf_counter()
    try:
        result = CANDIDATES[candidate](path)
    finally:
        signal.alarm(0)
    return {**result, "seconds": round(time.perf_counter() - start, 3)}


# PURPOSE: RUNS EVERY CANDIDATE ON EVERY CORPUS FILE AND WRITES THE RESULTS
def main() -> int:
    RESULTS.mkdir(parents=True, exist_ok=True)
    jobs = [  # RENAME: (CORPUS, CANDIDATE, FILE PATH) WORK ITEMS
        (corpus, candidate, str(p))
        for corpus, (base, pattern) in CORPORA.items()
        for p in sorted(base.glob(pattern))
        for candidate in CANDIDATES
    ]
    rows = []
    with ProcessPoolExecutor() as pool:
        futures = [(job, pool.submit(run_one, job[1], job[2])) for job in jobs]
        for (corpus, candidate, path), fut in futures:
            try:
                row = fut.result()
            except Exception as exc:  # a crash or SIGALRM timeout counts as a failed parse
                row = {"errors": None, "first_error_line": None, "seconds": None, "crash": repr(exc)}
            rows.append({"corpus": corpus, "candidate": candidate,
                         "file": str(Path(path).relative_to(ROOT)), **row})

    with open(RESULTS / "per_file.jsonl", "w") as fh:
        for row in rows:
            fh.write(json.dumps(row) + "\n")
    summary = summarize(rows)
    (RESULTS / "summary.md").write_text(summary)
    print(summary)
    return 0


# PURPOSE: BUILDS THE PARSE-RATE AND TIMING TABLE FOR ADR 001
def summarize(rows: list[dict]) -> str:
    lines = ["| Corpus | Candidate | Files | Parsed clean | Rate | Median s | Max s |",
             "|---|---|---|---|---|---|---|"]
    for corpus in CORPORA:
        for candidate in CANDIDATES:
            sel = [r for r in rows if r["corpus"] == corpus and r["candidate"] == candidate]
            ok = sum(1 for r in sel if r["errors"] == 0)
            times = sorted(r["seconds"] for r in sel if r["seconds"] is not None)
            median = times[len(times) // 2] if times else 0
            lines.append(f"| {corpus} | {candidate} | {len(sel)} | {ok} | "
                         f"{100 * ok / max(len(sel), 1):.1f}% | {median} | {max(times, default=0)} |")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
