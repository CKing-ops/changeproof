"""Just enough JCL to link batch steps to programs and datasets: JOB, PROC, EXEC and DD."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from changeproof.provenance import Provenance

STATEMENT_RE = re.compile(r"^//([A-Z@#$][A-Z0-9@#$.]{0,16})?\s+(JOB|PROC|EXEC|DD)\b\s*(.*)$", re.IGNORECASE)
CONTINUATION_RE = re.compile(r"^//\s+(\S.*)$")
MEMBER_RE = re.compile(r"\(.*\)$")  # a PDS member or GDG generation after the dataset name


@dataclass(frozen=True)
class JclDD:
    name: str
    dataset: str | None
    disp: str | None
    provenance: Provenance


@dataclass
class JclStep:
    name: str
    program: str | None
    proc: str | None
    provenance: Provenance
    dds: list[JclDD] = field(default_factory=list)


@dataclass
class JclJob:
    name: str
    kind: str  # JOB, or PROC for a cataloged procedure
    provenance: Provenance
    steps: list[JclStep] = field(default_factory=list)


# PURPOSE: SPLITS AN OPERAND FIELD ON TOP-LEVEL COMMAS, LEAVING PARENTHESES AND QUOTES WHOLE
def split_operands(text: str) -> list[str]:
    parts, depth, quoted, current = [], 0, False, []
    for ch in text:
        if ch == "'":
            quoted = not quoted
        elif not quoted and ch == "(":
            depth += 1
        elif not quoted and ch == ")":
            depth -= 1
        elif not quoted and depth == 0 and ch == ",":
            parts.append("".join(current))
            current = []
            continue
        current.append(ch)
    parts.append("".join(current))
    return [p for p in parts if p]


# PURPOSE: CUTS THE OPERAND FIELD AT THE FIRST BLANK OUTSIDE QUOTES; WHAT FOLLOWS IS A COMMENT
def operand_field(text: str) -> str:
    quoted = False
    for i, ch in enumerate(text):
        if ch == "'":
            quoted = not quoted
        elif ch == " " and not quoted:
            return text[:i]
    return text


# PURPOSE: GROUPS PHYSICAL LINES INTO STATEMENTS AS (NAME, OPERATION, OPERANDS, FIRST LINE, LAST LINE)
def statements(lines: list[str]):
    current = None  # RENAME: STATEMENT BEING ASSEMBLED ACROSS CONTINUATION LINES
    instream = False  # RENAME: INSIDE DD * OR DD DATA INPUT
    for number, raw in enumerate(lines, 1):
        line = raw[:72].rstrip()
        if instream:
            if line.startswith("//") and not line.startswith("//*") or line.startswith("/*"):
                instream = False
            if not line.startswith("//") or line.startswith("//*"):
                continue
        if line.startswith("//*") or not line.startswith("//"):
            continue
        if current and current[2].endswith(",") and (m := CONTINUATION_RE.match(line)) \
                and not STATEMENT_RE.match(line):
            current[2] += operand_field(m.group(1))
            current[4] = number
            continue
        if current:
            yield tuple(current)
            current = None
        if m := STATEMENT_RE.match(line):
            operands = operand_field(m.group(3))
            current = [(m.group(1) or "").upper(), m.group(2).upper(), operands, number, number]
            if m.group(2).upper() == "DD" and split_operands(operands)[:1] in (["*"], ["DATA"]):
                instream = True
    if current:
        yield tuple(current)


# PURPOSE: PARSES ONE JCL OR PROC MEMBER INTO JOBS, STEPS AND DD STATEMENTS WITH PROVENANCE
def parse_jcl(path: Path, root: Path) -> list[JclJob]:
    rel = Path(path).relative_to(root).as_posix()  # RENAME: REPO-RELATIVE PATH USED IN PROVENANCE
    lines = Path(path).read_text(encoding="latin-1").splitlines()
    jobs: list[JclJob] = []
    for name, op, operands, first, last in statements(lines):
        where = Provenance(file=rel, line=first, end_line=last if last != first else None)
        values = split_operands(operands)
        keywords = {k.upper(): v for k, sep, v in (p.partition("=") for p in values) if sep}
        if op in ("JOB", "PROC"):
            jobs.append(JclJob(name, op, where))
        elif op == "EXEC" and jobs:
            program = keywords.get("PGM")
            proc = keywords.get("PROC") or (values[0].upper() if values and "=" not in values[0] else None)
            jobs[-1].steps.append(JclStep(name, program.upper() if program else None, proc, where))
        elif op == "DD" and jobs and jobs[-1].steps:
            dsn = keywords.get("DSN") or keywords.get("DSNAME")
            dataset = MEMBER_RE.sub("", dsn).upper() if dsn else None
            jobs[-1].steps[-1].dds.append(JclDD(name, dataset, keywords.get("DISP"), where))
    return jobs
