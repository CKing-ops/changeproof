"""Just enough JCL to link batch steps to programs and datasets: JOB, PROC, EXEC and DD."""

import re
from dataclasses import dataclass, field
from pathlib import Path

from changeproof.adapters.base import Entity, IRModule
from changeproof.provenance import Provenance

STATEMENT_RE = re.compile(r"^//([A-Z@#$][A-Z0-9@#$.]{0,16})?\s+(JOB|PROC|EXEC|DD)\b\s*(.*)$", re.IGNORECASE)
CONTINUATION_RE = re.compile(r"^//\s+(\S.*)$")
MEMBER_RE = re.compile(r"\(.*\)$")  # a PDS member or GDG generation after the dataset name
RUN_PROGRAM_RE = re.compile(r"\bRUN\s+PROG(?:RAM)?\s*\(\s*([A-Z@#$][A-Z0-9@#$]{0,7})\s*\)", re.IGNORECASE)
TSO_PROGRAMS = frozenset({"IKJEFT01", "IKJEFT1A", "IKJEFT1B"})  # RENAME: TSO BATCH PROGRAMS THAT RUN WHAT SYSTSIN NAMES
IMS_PROGRAMS = frozenset({"DFSRRC00"})  # RENAME: IMS REGION CONTROLLERS WHOSE PARM NAMES THE PROGRAM
IMS_REGIONS = frozenset({"BMP", "DLI", "DBB"})  # RENAME: PARM REGION TYPES WHOSE SECOND FIELD IS THE PROGRAM


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
    runs: list[tuple[str, Provenance]] = field(default_factory=list)  # programs the step's program runs in turn


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


# PURPOSE: PROGRAMS NAMED BY RUN PROGRAM IN THE TSO INPUT AFTER AN EXEC, UP TO THE NEXT EXEC, JOB OR PROC
def tso_runs(lines: list[str], after: int, rel: str) -> list[tuple[str, Provenance]]:
    found = []
    for number in range(after + 1, len(lines) + 1):
        line = lines[number - 1][:72]
        if (m := STATEMENT_RE.match(line)) and m.group(2).upper() in ("EXEC", "JOB", "PROC"):
            break
        if not line.startswith("//*") and (m := RUN_PROGRAM_RE.search(line)):
            found.append((m.group(1).upper(), Provenance(file=rel, line=number)))
    return found


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
            program = keywords.get("PGM", "").upper() or None
            proc = keywords.get("PROC") or (values[0].upper() if values and "=" not in values[0] else None)
            step = JclStep(name, program, proc, where)
            fields = keywords.get("PARM", "").strip("()'").upper().split(",")
            if program in IMS_PROGRAMS and fields[0] in IMS_REGIONS and len(fields) > 1:
                step.runs.append((fields[1].strip("'"), where))
            if program in TSO_PROGRAMS:
                step.runs += tso_runs(lines, last, rel)
            jobs[-1].steps.append(step)
        elif op == "DD" and jobs and jobs[-1].steps:
            dsn = keywords.get("DSN") or keywords.get("DSNAME")
            dataset = MEMBER_RE.sub("", dsn).upper() if dsn else None
            jobs[-1].steps[-1].dds.append(JclDD(name, dataset, keywords.get("DISP"), where))
    return jobs


# PURPOSE: JCL AS IR ENTITIES (JOB, STEP, DD) SO TWO VERSIONS OF A MEMBER CAN BE DIFFED BY ID
def jcl_module(path: Path, root: Path) -> IRModule:
    entities = []
    for job in parse_jcl(path, root):
        scope = f"{job.kind.lower()}:{job.name}"
        entities.append(Entity(id=scope, kind=f"jcl-{job.kind.lower()}", name=job.name, provenance=job.provenance))
        for step in job.steps:
            step_id = f"{job.name}.{step.name}"
            entities.append(Entity(id=f"jcl-step:{step_id}", kind="jcl-step", name=step.name, provenance=step.provenance,
                                   attributes={"program": step.program, "proc": step.proc}))
            entities += [Entity(id=f"jcl-dd:{step_id}.{dd.name}", kind="jcl-dd", name=dd.name, provenance=dd.provenance,
                                attributes={"dataset": dd.dataset, "disp": dd.disp}) for dd in step.dds]
    return IRModule(path=Path(path).relative_to(root).as_posix(), language="jcl", entities=entities)
