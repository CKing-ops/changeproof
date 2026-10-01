"""Week 5 check on real code: impact recall on seeded CardDemo changes against a text-search oracle.

    uv run python scripts/impact_corpus_check.py

Seeds are entity-level changes: the first paragraph of every second program, the first 01-level
item of every second copybook a program copies, and the first DD of each step that runs a CardDemo
program. The oracle never touches the engine's parser or graph. It reads the source text and
finds, by regular expression, the programs that CALL, LINK or XCTL to a program (a quoted literal
of its name counts when the program also has a dynamic CALL, LINK or XCTL), the programs that COPY
a copybook, the JCL steps that run a program (EXEC PGM=, IKJEFT01 RUN PROGRAM, IMS DFSRRC00 PARM)
and the CSD transactions that start it, closed over callers. Recall is measured on programs, JCL
steps, jobs and transactions. Writes docs/weekly/week05-carddemo-impact.json.
"""

import json
import re
import sys
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from changeproof.adapters.base import ChangeKind, EntityChange
from changeproof.adapters.cobol import CobolAdapter
from changeproof.config import load_config
from changeproof.graph import graph_from
from changeproof.graph.csd import parse_csd
from changeproof.graph.jcl import jcl_module, parse_jcl
from changeproof.impact import ImpactWalk

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "carddemo"
COPYBOOK_DIRS = sorted(  # RENAME: CARDDEMO FOLDERS SEARCHED FOR COPYBOOKS AND DCLGEN MEMBERS
    p.relative_to(CORPUS).as_posix() for p in CORPUS.glob("app/**/*") if p.is_dir() and p.name in ("cpy", "cpy-bms", "dcl")
)
CONFIG = ROOT / "docs" / "examples" / "carddemo.yaml"
REPORT = ROOT / "docs" / "weekly" / "week05-carddemo-impact.json"
GATE_KINDS = frozenset({"program", "step", "job", "transaction"})  # RENAME: NODE KINDS THE ORACLE CAN JUDGE
COPY_RE = re.compile(r"\b(?:COPY|INCLUDE)\s+['\"]?([A-Z0-9@#$-]+)")


# PURPOSE: PARSES ONE PROGRAM IN A WORKER PROCESS
def parse_one(path: Path):
    return CobolAdapter(COPYBOOK_DIRS).parse(path, CORPUS)


# PURPOSE: SOURCE TEXT WITHOUT COMMENT LINES OR SEQUENCE AREAS, UPPERCASED
def code_text(path: Path) -> str:
    lines = path.read_text(encoding="latin-1").upper().splitlines()
    return "\n".join(line[7:72] for line in lines if len(line) > 6 and line[6] not in "*/")


class Oracle:
    # PURPOSE: READS EVERY PROGRAM, COPYBOOK, JCL MEMBER AND CSD EXTRACT AS PLAIN TEXT
    def __init__(self) -> None:
        files = [p for p in CORPUS.glob("app/**/*") if p.is_file()]
        self.copybooks = {p.stem.upper(): code_text(p) for p in files
                          if p.parent.name in ("cpy", "cpy-bms", "dcl") or p.suffix.lower() == ".cpy"}
        self.programs = {p.stem.upper(): self.expand(code_text(p), set()) for p in files if p.suffix.lower() == ".cbl"}
        self.jcl = {p.relative_to(CORPUS).as_posix(): p.read_text(encoding="latin-1").upper().splitlines()
                    for p in files if p.suffix.lower() in (".jcl", ".prc")}
        self.csd = "\n".join(p.read_text(encoding="latin-1").upper() for p in files if p.suffix.lower() == ".csd")

    # PURPOSE: INLINES COPYBOOKS, ONCE EACH, SO LITERALS DEFINED IN THEM COUNT
    def expand(self, text: str, seen: set[str]) -> str:
        parts = [text]
        for name in COPY_RE.findall(text):
            if name in self.copybooks and name not in seen:
                seen.add(name)
                parts.append(self.expand(self.copybooks[name], seen))
        return "\n".join(parts)

    # PURPOSE: PROGRAMS THAT CALL, LINK OR XCTL TO A PROGRAM, BY LITERAL OR THROUGH A DYNAMIC TARGET
    def callers(self, name: str) -> set[str]:
        literal = re.compile(rf"(?:CALL\s+'{name}'|PROGRAM\s*\(\s*'{name}'\s*\))")
        quoted = f"'{name}'"
        dynamic = re.compile(r"\b(?:CALL\s+[A-Z]|XCTL|LINK)\b")
        return {p for p, text in self.programs.items()
                if p != name and (literal.search(text) or quoted in text and dynamic.search(text))}

    # PURPOSE: PROGRAMS WHOSE TEXT COPIES A COPYBOOK, DIRECTLY OR THROUGH ANOTHER COPYBOOK
    def copiers(self, book: str) -> set[str]:
        pattern = re.compile(rf"\b(?:COPY|INCLUDE)\s+['\"]?{re.escape(book)}\b")
        return {p for p, text in self.programs.items() if pattern.search(text)}

    # PURPOSE: (JOB, STEP) PAIRS WHOSE STEP RUNS A PROGRAM, DIRECTLY OR THROUGH IKJEFT01 OR DFSRRC00
    def steps(self, name: str) -> set[tuple[str, str]]:
        found = set()
        for lines in self.jcl.values():
            job = step = None
            for line in lines:
                if m := re.match(r"^//([A-Z0-9@#$]+)\s+(?:JOB|PROC)\b", line):
                    job = m.group(1)
                elif m := re.match(r"^//([A-Z0-9@#$]+)\s+EXEC\s+(.*)", line):
                    step = m.group(1)
                    if re.search(rf"PGM={name}\b", m.group(2)):
                        found.add((job, step))
                if step and (re.search(rf"RUN\s+PROGRAM\s*\(\s*{name}\s*\)", line)
                             or re.search(rf"PARM=\(?'?(?:BMP|DLI|MPP),{name},", line)):
                    found.add((job, step))
        return found

    # PURPOSE: CSD TRANSACTIONS WHOSE DEFINITION NAMES THE PROGRAM
    def transactions(self, name: str) -> set[str]:
        return {m.group(1) for m in re.finditer(r"DEFINE\s+TRANSACTION\((\w+)\)([^\n]*(?:\n(?!\s*DEFINE)[^\n]*)*)", self.csd)
                if re.search(rf"PROGRAM\({name}\)", m.group(2))}

    # PURPOSE: EXPECTED IMPACTED IDS FOR A SET OF DIRECTLY CHANGED PROGRAMS, CLOSED OVER CALLERS
    def expected(self, programs: set[str]) -> set[str]:
        reached, todo = set(programs), list(programs)
        while todo:
            for caller in self.callers(todo.pop()) - reached:
                reached.add(caller)
                todo.append(caller)
        found = {f"program:{p}" for p in reached}
        for p in reached:
            found |= {f"step:{job}.{step}" for job, step in self.steps(p)} | {f"job:{job}" for job, _ in self.steps(p)}
            found |= {f"transaction:{t}" for t in self.transactions(p)}
        return found


# PURPOSE: SEEDED ENTITY CHANGES, AS (NAME, CHANGES, PROGRAMS THE ORACLE STARTS FROM)
def seeds(modules, jcl_modules, graph) -> list[tuple[str, list[EntityChange], set[str]]]:
    found = []
    programs = sorted(modules, key=lambda m: m.path)
    for module in programs[::2]:
        paragraph = next((e for e in module.entities if e.kind == "paragraph"), None)
        if paragraph:
            name = paragraph.id.split(":", 1)[1].split(".", 1)[0]
            found.append((f"paragraph {paragraph.id}", [EntityChange(change=ChangeKind.MODIFIED, entity=paragraph,
                                                                    previous=paragraph)], {name}))
    copied = sorted({e.attributes["resolved"] for m in modules for e in m.entities
                     if e.kind == "copybook" and e.attributes["resolved"]})
    for book in copied[::2]:
        firsts = [next((e for e in m.entities if e.kind == "data" and e.provenance.file == book
                        and e.attributes.get("level") == "01"), None) for m in modules]
        changes = [EntityChange(change=ChangeKind.MODIFIED, entity=e, previous=e) for e in firsts if e]
        if changes:
            found.append((f"copybook {book}", changes, {e.id.split(":", 1)[1].split(".", 1)[0] for e in
                                                          (c.entity for c in changes)}))
    runs = {e.src: e.dst.split(":", 1)[1] for e in graph.edges if e.kind == "runs" and e.resolved}
    for module in jcl_modules:
        for e in module.entities:
            step = "step:" + e.id.split(":", 1)[1].rsplit(".", 1)[0]
            if e.kind == "jcl-dd" and step in runs:
                found.append((f"dd {e.id}", [EntityChange(change=ChangeKind.MODIFIED, entity=e, previous=e)],
                              {runs.pop(step)}))
    return found


# PURPOSE: RUNS EVERY SEED THROUGH THE ENGINE AND THE ORACLE, WRITES THE REPORT, EXITS 1 BELOW 95% RECALL
def main() -> int:
    paths = sorted(p for p in CORPUS.glob("app/**/*") if p.suffix.lower() == ".cbl")
    with ProcessPoolExecutor() as pool:
        return check(list(pool.map(parse_one, paths)))


# PURPOSE: SCORES THE ENGINE AGAINST THE ORACLE ON ALREADY-PARSED PROGRAMS
def check(modules) -> int:
    jcl_paths = sorted(p for p in CORPUS.glob("app/**/*") if p.suffix.lower() in (".jcl", ".prc"))
    jobs = [job for path in jcl_paths for job in parse_jcl(path, CORPUS)]
    csd = [d for path in CORPUS.glob("app/**/*.csd") for d in parse_csd(path, CORPUS)]
    graph = graph_from(modules, jobs, load_config(CONFIG), csd)
    walk = ImpactWalk(graph)
    oracle = Oracle()
    rows, hit, total = [], 0, 0
    for name, changes, start in seeds(modules, [jcl_module(p, CORPUS) for p in jcl_paths], graph):
        best, changed = walk.walk(changes)
        engine = {n: r.tier.name.lower() for n, r in best.items()
                  if walk.nodes[n].kind in GATE_KINDS and n not in changed}
        expected = oracle.expected(start) - changed
        missed = sorted(expected - set(engine))
        hit += len(expected) - len(missed)
        total += len(expected)
        rows.append({"seed": name, "expected": len(expected), "found": len(expected) - len(missed), "missed": missed,
                     "engine_only": sorted(set(engine) - expected),
                     "tiers": {t: sum(1 for n in expected if engine.get(n) == t) for t in ("definite", "probable", "possible")}})
    recall = hit / total
    REPORT.write_text(json.dumps({"seeds": len(rows), "expected": total, "found": hit, "recall": round(recall, 4),
                                  "rows": rows}, indent=1) + "\n")
    print(f"{len(rows)} seeds, {hit} of {total} expected entities found, recall {recall:.1%}")
    for row in rows:
        if row["missed"]:
            print(f"  {row['seed']}: missed {', '.join(row['missed'])}")
    return 0 if recall >= 0.95 else 1


if __name__ == "__main__":
    sys.exit(main())
