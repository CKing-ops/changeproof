"""COBOL text manipulation that runs before parsing: COPY, REPLACE and EXEC.

Every output line keeps the file and line it came from, so a fact the parser finds in an inlined
copybook points at the copybook, not at the program that copied it (CLAUDE.md rule 2).
"""

import bisect
import re
from dataclasses import dataclass, field, replace
from pathlib import Path

COPY_SUFFIXES = ("", ".cpy", ".CPY", ".cbl", ".CBL", ".cob", ".COB")  # RENAME: EXTENSIONS TRIED FOR A COPYBOOK NAME
MAX_COPY_DEPTH = 16  # RENAME: DEEPEST COPY NESTING FOLLOWED

# Literals never cross a line break here; continued literals are joined before any regex runs.
TOKEN_RE = re.compile(
    r"==.*?==|'[^'\n]*'?|\"[^\"\n]*\"?|[.,;](?=\s|$)|[()]|[^\s'\"()]+?(?=[.,;](?:\s|$)|[\s'\"()]|$)",
    re.DOTALL,
)
LITERAL_RE = re.compile(r"'[^'\n]*'?|\"[^\"\n]*\"?")
PARTIAL_WORD_RE = re.compile(r"^(?:\(\S+\)|:\S+:)$")
EXEC_RE = re.compile(r"(?<![\w-])EXEC\s+(SQL|CICS|DLI)\b(.*?)\bEND-EXEC\b", re.IGNORECASE | re.DOTALL)
PROCEDURE_RE = re.compile(r"(?<![\w-])PROCEDURE\s+DIVISION\b", re.IGNORECASE)
DIRECTIVE_RE = re.compile(r"^\s*(?:EJECT|SKIP[123])\s*\.?\s*$|^\s*(?:CBL|PROCESS)\s", re.IGNORECASE)


@dataclass
class Line:
    text: str  # code area only (columns 8-72), continuation lines already joined
    file: str
    line: int
    end_line: int | None = None


@dataclass(frozen=True)
class CopyStatement:
    name: str
    file: str
    line: int
    resolved: str | None
    replacing: list[tuple[str, str]] = field(default_factory=list)
    problem: str | None = None
    end_line: int | None = None  # last line of a statement that spans lines


@dataclass(frozen=True)
class ExecBlock:
    kind: str  # SQL, CICS or DLI
    text: str  # the statement between EXEC <kind> and END-EXEC, whitespace collapsed
    file: str
    line: int
    end_line: int
    index: int  # position in Source.lines where the block now reads CONTINUE or blanks


@dataclass
class Source:
    lines: list[Line]
    copies: list[CopyStatement]
    execs: list[ExecBlock]


class CopybookLibrary:
    # PURPOSE: REMEMBERS WHERE TO LOOK FOR COPYBOOKS, AS PATHS RELATIVE TO THE REPO ROOT
    def __init__(self, root: Path, search: list[str]) -> None:
        self.root = Path(root)
        self.dirs = [self.root / d for d in search]  # RENAME: COPYBOOK FOLDERS, IN SEARCH ORDER

    # PURPOSE: FINDS A COPYBOOK FILE BY NAME, IGNORING CASE, AND RETURNS ITS PATH OR NONE
    def find(self, name: str) -> Path | None:
        for folder in self.dirs:
            for candidate in (name, name.upper(), name.lower()):
                for suffix in COPY_SUFFIXES:
                    path = folder / f"{candidate}{suffix}"
                    if path.is_file():
                        return path
        return None


# PURPOSE: READS FIXED-FORMAT SOURCE INTO CODE-AREA LINES, DROPPING COMMENTS AND JOINING CONTINUATIONS
def read_fixed_format(path: Path, root: Path) -> list[Line]:
    rel = Path(path).relative_to(root).as_posix()  # RENAME: REPO-RELATIVE PATH USED IN PROVENANCE
    lines: list[Line] = []
    for number, raw in enumerate(Path(path).read_text(encoding="latin-1").splitlines(), 1):
        indicator = raw[6] if len(raw) > 6 else " "
        area = raw[7:72]
        if indicator in "*/dD" or DIRECTIVE_RE.match(area):
            continue
        area = strip_inline_comment(area)
        if indicator == "-" and lines:
            prev = lines[-1]
            prev.text = join_continuation(prev.text, area)
            prev.end_line = number
        elif area.strip():
            lines.append(Line(area.rstrip(), rel, number))
    return lines


# PURPOSE: DROPS A FLOATING *> COMMENT THAT STARTS OUTSIDE A LITERAL
def strip_inline_comment(area: str) -> str:
    pos = 0
    for m in LITERAL_RE.finditer(area):
        if (cut := area.find("*>", pos, m.start())) != -1:
            return area[:cut]
        pos = m.end()
    cut = area.find("*>", pos)
    return area if cut == -1 else area[:cut]


# PURPOSE: APPENDS A CONTINUATION LINE, KEEPING THE TRAILING SPACES OF AN OPEN LITERAL
def join_continuation(prev: str, area: str) -> str:
    open_quote = None  # RENAME: QUOTE CHARACTER OF A LITERAL STILL OPEN AT END OF LINE
    for ch in prev:
        if open_quote and ch == open_quote:
            open_quote = None
        elif not open_quote and ch in "'\"":
            open_quote = ch
    if open_quote:
        body = area.lstrip()
        return prev.ljust(65) + (body[1:] if body.startswith(open_quote) else body)
    return prev.rstrip() + area.lstrip()


# PURPOSE: RUNS THE WHOLE PREPROCESSOR ON ONE PROGRAM AND RETURNS LINES WITH PROVENANCE
def preprocess(path: Path, root: Path, library: CopybookLibrary) -> Source:
    copies: list[CopyStatement] = []
    lines = expand_copies(read_fixed_format(path, root), library, copies, stack=())
    lines = apply_replace_statements(lines)
    lines, execs = mask_exec_blocks(lines)
    return Source(drop_separators(lines), copies, execs)


# PURPOSE: FINDS THE NEXT COPY OR EXEC SQL INCLUDE STATEMENT AND RETURNS ITS PARTS
def next_copy(joined: str) -> tuple[int, int, str, list[tuple[str, str]]] | None:
    tokens = list(TOKEN_RE.finditer(joined))
    for i, tok in enumerate(tokens):
        word = tok.group().upper()
        if word == "COPY" and i + 1 < len(tokens):
            name = tokens[i + 1].group().strip("'\"")
            j = i + 2
            while j < len(tokens) and tokens[j].group().upper() in ("OF", "IN", "SUPPRESS"):
                j += 2 if tokens[j].group().upper() != "SUPPRESS" else 1
            pairs = []  # RENAME: REPLACING OPERANDS AS (FROM, TO) TEXT
            if j < len(tokens) and tokens[j].group().upper() == "REPLACING":
                j += 1
                while j + 2 < len(tokens) and tokens[j + 1].group().upper() == "BY":
                    pairs.append((operand(tokens[j].group()), operand(tokens[j + 2].group())))
                    j += 3
            end = tokens[j].end() if j < len(tokens) and tokens[j].group() == "." else tokens[j - 1].end()
            return tok.start(), end, name, pairs
        if word == "EXEC" and i + 3 < len(tokens) and tokens[i + 1].group().upper() == "SQL" \
                and tokens[i + 2].group().upper() == "INCLUDE":
            j = i + 4
            if j < len(tokens) and tokens[j].group().upper() == "END-EXEC":
                end = tokens[j + 1].end() if j + 1 < len(tokens) and tokens[j + 1].group() == "." else tokens[j].end()
                return tok.start(), end, tokens[i + 3].group().strip("'\""), []
    return None


# PURPOSE: STRIPS PSEUDO-TEXT DELIMITERS AND COLLAPSES WHITESPACE IN A REPLACING OPERAND
def operand(text: str) -> str:
    if text.startswith("==") and text.endswith("=="):
        text = text[2:-2]
    return " ".join(text.split())


# PURPOSE: SPLICES EACH COPYBOOK IN PLACE OF ITS COPY STATEMENT, RECURSIVELY
def expand_copies(lines: list[Line], library: CopybookLibrary, copies: list[CopyStatement],
                  stack: tuple[str, ...]) -> list[Line]:
    while True:
        joined, starts = join_lines(lines)
        found = next_copy(joined)
        if found is None:
            return lines
        start, end, name, pairs = found
        first, last = locate(starts, start), locate(starts, end - 1)
        at = lines[first]  # RENAME: LINE HOLDING THE COPY KEYWORD
        path = library.find(name)
        resolved = path.relative_to(library.root).as_posix() if path else None
        problem = None  # RENAME: WHY THE COPYBOOK WAS NOT INLINED, IF IT WASN'T
        body: list[Line] = []
        if path is None:
            problem = "copybook not found"
        elif name.upper() in stack or len(stack) >= MAX_COPY_DEPTH:
            problem = "recursive COPY"
        else:
            body = expand_copies(read_fixed_format(path, library.root), library, copies, stack + (name.upper(),))
            for old, new in pairs:
                body = apply_replacing(body, old, new)
        last_line = lines[last].end_line or lines[last].line  # RENAME: LAST SOURCE LINE OF THE STATEMENT
        spans = lines[last].file == at.file and last_line > at.line
        copies.append(CopyStatement(name.upper(), at.file, at.line, resolved, pairs, problem,
                                    last_line if spans else None))
        prefix = lines[first].text[: start - starts[first]]
        suffix = lines[last].text[end - starts[last]:]
        spliced = [replace(at, text=prefix)] if prefix.strip() else []
        spliced += body
        spliced += [replace(lines[last], text=suffix)] if suffix.strip() else []
        lines = lines[:first] + spliced + lines[last + 1:]


# PURPOSE: JOINS LINE TEXTS WITH NEWLINES AND RETURNS EACH LINE'S START OFFSET
def join_lines(lines: list[Line]) -> tuple[str, list[int]]:
    starts, pos = [], 0
    for ln in lines:
        starts.append(pos)
        pos += len(ln.text) + 1
    return "\n".join(ln.text for ln in lines), starts


# PURPOSE: MAPS A CHARACTER OFFSET IN THE JOINED TEXT BACK TO ITS LINE INDEX
def locate(starts: list[int], offset: int) -> int:
    return bisect.bisect_right(starts, offset) - 1


# PURPOSE: SPLITS JOINED TEXT BACK INTO LINES; THE CALLER KEEPS THE NEWLINE COUNT UNCHANGED
def split_back(lines: list[Line], joined: str) -> list[Line]:
    texts = joined.split("\n")
    assert len(texts) == len(lines), "a rewrite changed the line count"
    return [replace(ln, text=t) for ln, t in zip(lines, texts)]


# PURPOSE: REPLACES A SPAN BUT KEEPS ITS LINE BREAKS SO EVERY LINE KEEPS ITS PROVENANCE
def splice(joined: str, start: int, end: int, new: str) -> str:
    return joined[:start] + new + "\n" * joined.count("\n", start, end) + joined[end:]


# PURPOSE: COMPARABLE FORM OF A TEXT-WORD: WORDS IGNORE CASE, LITERALS DO NOT
def word_key(token: str) -> str:
    return token if token[:1] in "'\"" else token.upper()


# PURPOSE: APPLIES ONE REPLACING OR REPLACE PAIR TO A RUN OF LINES
def apply_replacing(lines: list[Line], old: str, new: str) -> list[Line]:
    return split_back(lines, replace_text(join_lines(lines)[0], old, new))


# PURPOSE: REPLACES TEXT-WORD SEQUENCES (OR A TAGGED PARTIAL WORD) WITHOUT CHANGING THE LINE COUNT
def replace_text(joined: str, old: str, new: str) -> str:
    if PARTIAL_WORD_RE.match(old):
        pattern = re.compile(re.escape(old), re.IGNORECASE)
        parts = LITERAL_RE.split(joined)
        literals = LITERAL_RE.findall(joined)
        rebuilt = pattern.sub(lambda _: new, parts[0])
        for lit, part in zip(literals, parts[1:]):
            rebuilt += lit + pattern.sub(lambda _: new, part)
        return rebuilt
    target = [word_key(t) for t in TOKEN_RE.findall(old) if t not in (",", ";")]
    tokens = [t for t in TOKEN_RE.finditer(joined) if t.group() not in (",", ";")]
    keys = [word_key(t.group()) for t in tokens]
    hits, i = [], 0
    while target and i <= len(keys) - len(target):
        if keys[i:i + len(target)] == target:
            hits.append((tokens[i].start(), tokens[i + len(target) - 1].end()))
            i += len(target)
        else:
            i += 1
    for start, end in reversed(hits):
        joined = splice(joined, start, end, new)
    return joined


# PURPOSE: APPLIES REPLACE ... REPLACE OFF STATEMENTS TO THE TEXT THAT FOLLOWS THEM
def apply_replace_statements(lines: list[Line]) -> list[Line]:
    joined, _ = join_lines(lines)
    tokens = list(TOKEN_RE.finditer(joined))
    statements = []  # RENAME: (START, END, PAIRS) PER REPLACE STATEMENT; EMPTY PAIRS MEAN OFF
    i = 0
    while i < len(tokens):
        nxt = tokens[i + 1].group() if i + 1 < len(tokens) else ""
        if tokens[i].group().upper() == "REPLACE" and (nxt.startswith("==") or nxt.upper() == "OFF"):
            j = i + 2 if nxt.upper() == "OFF" else i + 1
            pairs = []
            while j + 2 < len(tokens) and tokens[j + 1].group().upper() == "BY":
                pairs.append((operand(tokens[j].group()), operand(tokens[j + 2].group())))
                j += 3
            end = tokens[j].end() if j < len(tokens) and tokens[j].group() == "." else tokens[j - 1].end()
            statements.append((tokens[i].start(), end, pairs))
            i = j + 1
        else:
            i += 1
    stops = [start for start, _, _ in statements[1:]] + [len(joined)]  # RENAME: WHERE EACH STATEMENT'S EFFECT ENDS
    for (start, end, pairs), stop in reversed(list(zip(statements, stops))):
        region = joined[end:stop]
        for old, new in pairs:
            region = replace_text(region, old, new)
        joined = splice(joined[:end] + region + joined[stop:], start, end, "")
    return split_back(lines, joined)


# PURPOSE: PULLS EACH EXEC BLOCK OUT AS A RECORD AND LEAVES CONTINUE (OR BLANKS) IN ITS PLACE
def mask_exec_blocks(lines: list[Line]) -> tuple[list[Line], list[ExecBlock]]:
    joined, starts = join_lines(lines)
    proc = PROCEDURE_RE.search(joined)
    execs = []
    for m in reversed(list(EXEC_RE.finditer(joined))):
        first, last = locate(starts, m.start()), locate(starts, m.end() - 1)
        end_line = lines[last].end_line or lines[last].line
        execs.append(ExecBlock(m.group(1).upper(), " ".join(m.group(2).split()), lines[first].file,
                               lines[first].line, end_line, first))
        joined = splice(joined, m.start(), m.end(), "CONTINUE" if proc and m.start() > proc.start() else "")
    return split_back(lines, joined), execs[::-1]


# PURPOSE: TURNS SEPARATOR COMMAS AND SEMICOLONS INTO SPACES, LEAVING LITERALS ALONE
def drop_separators(lines: list[Line]) -> list[Line]:
    out = []
    for ln in lines:
        parts = LITERAL_RE.split(ln.text)
        literals = LITERAL_RE.findall(ln.text)
        text = re.sub(r"[,;](?=\s|$)", " ", parts[0])
        for lit, part in zip(literals, parts[1:]):
            text += lit + re.sub(r"[,;](?=\s|$)", " ", part)
        out.append(replace(ln, text=text))
    return out
