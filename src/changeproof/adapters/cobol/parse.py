"""Runs the generated Cobol85 parser (ADR 001) over preprocessed lines.

ANTLR sees one text line per preprocessed line, so a token's line number is an index into
Source.lines and maps straight back to file:line.
"""

import re
import sys
import threading

from antlr4 import CommonTokenStream, InputStream
from antlr4.error.ErrorListener import ErrorListener

from changeproof.adapters.cobol._generated.Cobol85Lexer import Cobol85Lexer
from changeproof.adapters.cobol._generated.Cobol85Parser import Cobol85Parser
from changeproof.adapters.cobol.preprocess import Source
from changeproof.provenance import Provenance

STACK_BYTES = 512 * 1024 * 1024  # RENAME: THREAD STACK FOR DEEPLY NESTED CONDITIONS
RECURSION_LIMIT = 200_000  # RENAME: PYTHON RECURSION LIMIT WHILE PARSING

COMMENT_ENTRY_RE = re.compile(
    r"^(\s*(?:AUTHOR|INSTALLATION|DATE-WRITTEN|DATE-COMPILED|SECURITY|REMARKS)\s*\.)(.*)$", re.IGNORECASE
)
ID_PARAGRAPH_RE = re.compile(r"^\s*(?:PROGRAM-ID|AUTHOR|INSTALLATION|DATE-WRITTEN|DATE-COMPILED|SECURITY|REMARKS)\s*\.",
                             re.IGNORECASE)
DIVISION_RE = re.compile(r"^\s*(ENVIRONMENT|DATA|PROCEDURE)\s+DIVISION\b", re.IGNORECASE)


class CobolSyntaxError(ValueError):
    # PURPOSE: CARRIES EVERY SYNTAX ERROR WITH THE FILE:LINE IT CAME FROM
    def __init__(self, errors: list[tuple[Provenance, str]]) -> None:
        self.errors = errors
        shown = "; ".join(f"{where}: {msg}" for where, msg in errors[:5])
        more = f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""
        super().__init__(f"{len(errors)} syntax error(s): {shown}{more}")


class Collect(ErrorListener):
    # PURPOSE: STARTS AN EMPTY LIST OF (LINE, MESSAGE) PAIRS
    def __init__(self) -> None:
        self.found: list[tuple[int, str]] = []

    # PURPOSE: RECORDS WHERE ANTLR REPORTED A SYNTAX ERROR
    def syntaxError(self, recognizer, offending, line, column, msg, e):
        self.found.append((line, msg))


# PURPOSE: TAGS IDENTIFICATION-DIVISION COMMENT ENTRIES (AUTHOR. ETC.) THE WAY THE GRAMMAR EXPECTS
def tag_comment_entries(texts: list[str]) -> list[str]:
    out, in_entry = list(texts), False
    for i, text in enumerate(out):
        if DIVISION_RE.match(text):
            break
        if m := COMMENT_ENTRY_RE.match(text):
            in_entry = True
            out[i] = m.group(1) + (f" *>CE {m.group(2).strip()}" if m.group(2).strip() else "")
        elif ID_PARAGRAPH_RE.match(text):
            in_entry = False
        elif in_entry and text.strip():
            out[i] = f" *>CE {text.strip()}"
    return out


# PURPOSE: MAPS A 1-BASED ANTLR LINE BACK TO THE SOURCE FILE AND LINE
def provenance_of(source: Source, antlr_line: int) -> Provenance:
    ln = source.lines[min(antlr_line, len(source.lines)) - 1]
    return Provenance(file=ln.file, line=ln.line, end_line=ln.end_line)


# PURPOSE: LEXES AND PARSES THE PREPROCESSED LINES, RAISING ON ANY SYNTAX ERROR
def parse_tree(source: Source):
    # Two-stage SLL-then-LL parsing was tried; SLL gives up on ordinary subscripts such as
    # ARR(1) in this grammar, so it only added time.
    text = "\n".join(" " + t for t in tag_comment_entries([ln.text for ln in source.lines])) + "\n"
    collect = Collect()
    lexer = Cobol85Lexer(InputStream(text))
    lexer.removeErrorListeners()
    lexer.addErrorListener(collect)
    tokens = CommonTokenStream(lexer)
    parser = Cobol85Parser(tokens)
    parser.removeErrorListeners()
    parser.addErrorListener(collect)
    tree = parser.startRule()
    if collect.found:
        raise CobolSyntaxError([(provenance_of(source, line), msg) for line, msg in collect.found])
    return tree, tokens


# PURPOSE: RUNS PARSE_TREE IN A THREAD WITH A LARGE STACK SO DEEP NESTING DOES NOT OVERFLOW
def parse(source: Source):
    result: dict = {}

    # PURPOSE: THREAD BODY; STORES THE TREE OR THE EXCEPTION FOR THE CALLER
    def work() -> None:
        try:
            result["value"] = parse_tree(source)
        except BaseException as exc:  # re-raised in the calling thread below
            result["error"] = exc

    old_stack, old_limit = threading.stack_size(STACK_BYTES), sys.getrecursionlimit()
    sys.setrecursionlimit(RECURSION_LIMIT)
    try:
        worker = threading.Thread(target=work)
        worker.start()
        worker.join()
    finally:
        threading.stack_size(old_stack)
        sys.setrecursionlimit(old_limit)
    if "error" in result:
        raise result["error"]
    return result["value"]
