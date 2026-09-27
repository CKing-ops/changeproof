"""Builds the dependency graph from IR modules and JCL (ROADMAP Week 3).

Every edge comes from one IR fact or JCL statement and carries its provenance. An edge whose
target is not in the analyzed code still goes in the graph, pointing at an `unresolved:` stub node
with the reason, so gaps are reported instead of silently dropped.
"""

import re
from pathlib import Path

from changeproof.adapters.base import Entity, IRModule
from changeproof.adapters.cobol import CobolAdapter
from changeproof.config import Config
from changeproof.graph.jcl import JclJob, parse_jcl
from changeproof.graph.model import Edge, Graph, Node
from changeproof.provenance import Provenance

SQL_WORD_RE = re.compile(r"[\w.$#@:-]+|[(),]")
CICS_FILE_COMMANDS = frozenset({  # RENAME: CICS COMMANDS THAT READ OR WRITE A FILE
    "READ", "WRITE", "REWRITE", "DELETE", "STARTBR", "READNEXT", "READPREV", "ENDBR", "RESETBR", "UNLOCK",
})
DD_PREFIX_RE = re.compile(r"^(?:[A-Z]{2}-)*(?:S-)?")  # ASSIGN TO UT-S-NAME style prefixes before the DD name


SQL_CLAUSES = frozenset({  # RENAME: KEYWORDS THAT END A FROM LIST
    "WHERE", "JOIN", "INNER", "LEFT", "RIGHT", "FULL", "CROSS", "ON", "GROUP", "ORDER", "HAVING", "UNION",
    "FETCH", "FOR", "WITH", "EXCEPT", "INTERSECT", "OPTIMIZE", "QUERYNO", "SKIP", "SET", "VALUES",
})


# PURPOSE: LISTS (TABLE, READS OR WRITES) FOR EVERY TABLE AN SQL STATEMENT NAMES
def sql_tables(text: str) -> list[tuple[str, str]]:
    words = SQL_WORD_RE.findall(text.upper())
    found: list[tuple[str, str]] = []
    for i, word in enumerate(words):
        before = words[i - 1] if i else ""
        if word == "UPDATE" or (word == "INTO" and before == "INSERT") or (word == "FROM" and before == "DELETE"):
            mode = "writes"
        elif word in ("FROM", "JOIN"):
            mode = "reads"
        else:
            continue
        j = i + 1
        while j < len(words) and words[j] != "(" and not words[j].startswith(":") and words[j] not in SQL_CLAUSES:
            found.append((words[j], mode))
            if not (word == "FROM" and mode == "reads"):
                break
            j += 1
            while j < len(words) and words[j] not in (",", ")") and words[j] not in SQL_CLAUSES:
                j += 1  # skips a correlation name
            if j >= len(words) or words[j] != ",":
                break
            j += 1
    return found


class GraphBuilder:
    # PURPOSE: STARTS AN EMPTY GRAPH WITH LOOKUPS FILLED IN AS MODULES ARE ADDED
    def __init__(self) -> None:
        self.nodes: dict[str, Node] = {}
        self.edges: dict[str, Edge] = {}
        self.programs: set[str] = set()
        self.facts: dict[str, list[Entity]] = {}  # RENAME: PROGRAM NAME TO ITS IR ENTITIES

    # PURPOSE: ADDS A NODE ONCE; THE FIRST PROVENANCE SEEN WINS
    def node(self, node_id: str, kind: str, name: str, where: Provenance, attributes: dict | None = None) -> str:
        if node_id not in self.nodes:
            self.nodes[node_id] = Node(id=node_id, kind=kind, name=name, provenance=where, attributes=attributes or {})
        return node_id

    # PURPOSE: ADDS AN EDGE KEYED BY THE FACT IT CAME FROM
    def edge(self, key: str, src: str, dst: str, kind: str, where: Provenance, **attributes) -> None:
        self.edges[key] = Edge(key=key, src=src, dst=dst, kind=kind, provenance=where, attributes=attributes)

    # PURPOSE: ADDS AN EDGE TO A STUB NODE FOR A TARGET THE ANALYZED CODE DOES NOT CONTAIN
    def unresolved(self, key: str, src: str, target: str, kind: str, where: Provenance, reason: str, **attributes) -> None:
        stub = self.node(f"unresolved:{target}", "unresolved", target.split(":", 1)[1], where)
        self.edges[key] = Edge(key=key, src=src, dst=stub, kind=kind, provenance=where, resolved=False,
                               attributes={"reason": reason} | attributes)

    # PURPOSE: INDEXES PROGRAMS FIRST SO CALLS BETWEEN MODULES RESOLVE IN ANY ORDER
    def index(self, modules: list[IRModule]) -> None:
        for module in modules:
            for e in module.entities:
                if e.kind == "program":
                    self.programs.add(e.name)
                    self.node(e.id, "program", e.name, e.provenance, {"module": module.path})
                program = e.id.split(":", 1)[1].split(".", 1)[0].split("#", 1)[0]
                self.facts.setdefault(program, []).append(e)

    # PURPOSE: FINDS THE PARAGRAPH OR SECTION A PERFORM OR GO TO NAMES, PREFERRING THE CALLER'S SECTION
    def procedure(self, program: str, name: str, caller: str | None, in_section: str | None) -> str | None:
        facts = self.facts[program]
        paragraphs = [e for e in facts if e.kind == "paragraph" and e.name == name]
        if in_section:
            paragraphs = [e for e in paragraphs if e.attributes.get("section") == f"section:{program}.{in_section}"]
        caller_section = next((e.attributes.get("section") for e in facts if e.id == caller), None)
        same = [e for e in paragraphs if e.attributes.get("section") == caller_section]
        if same or paragraphs:
            return (same or paragraphs)[0].id
        return next((e.id for e in facts if e.kind == "section" and e.name == name), None)

    # PURPOSE: LITERALS A DATA ITEM CAN HOLD, FROM ITS VALUE CLAUSE AND FROM MOVES, AS (VALUE, SOURCE FACT ID)
    def values_of(self, program: str, data_name: str) -> list[tuple[str, str]]:
        found = {}  # RENAME: LITERAL TO THE FIRST FACT THAT PUTS IT IN THE DATA ITEM
        for e in self.facts[program]:
            if e.kind == "data" and e.name == data_name and "value" in e.attributes:
                found.setdefault(e.attributes["value"].strip().upper(), e.id)
            elif e.kind == "flow" and "literal" in e.attributes and \
                    any(t.split()[0] == data_name for t in e.attributes["targets"]):
                found.setdefault(e.attributes["literal"].strip().upper(), e.id)
        return list(found.items())

    # PURPOSE: FINDS THE DATA ITEM A NAME LIKE "FIELD OF GROUP" REFERS TO, OR THE REASON IT CANNOT
    def data_item(self, program: str, ref: str) -> tuple[str | None, str]:
        name, *qualifiers = ref.split(" OF ")
        matches = [e.id for e in self.facts[program] if e.kind == "data" and e.name == name
                   and set(qualifiers) <= set(e.id.split(":", 1)[1].split(".")[1:-1])]
        if len(matches) == 1:
            return matches[0], ""
        return None, f"ambiguous: {len(matches)} data items have this name" if matches else "no such data item"

    # PURPOSE: TURNS ONE PROGRAM'S IR FACTS INTO NODES AND EDGES
    def add_program(self, program: str) -> None:
        home = f"program:{program}"
        for e in self.facts[program]:
            src = e.attributes.get("paragraph", home)
            match e.kind:
                case "paragraph" | "section":
                    self.node(e.id, e.kind, e.name, e.provenance, {k: v for k, v in e.attributes.items() if k != "text"})
                    self.edge(f"contains>{e.id}", home, e.id, "contains", e.provenance)
                case "perform" | "goto":
                    self.add_jump(program, e, src)
                case "call":
                    self.add_call(program, e, src)
                case "crypto-call":
                    service = self.node(f"crypto-service:{e.attributes['service']}", "crypto-service",
                                        e.attributes["service"], e.provenance, {"category": e.attributes["category"]})
                    self.edge(e.id, src, service, "uses-crypto", e.provenance,
                              category=e.attributes["category"], via=e.attributes["via"])
                case "copybook":
                    self.add_copybook(e, home)
                case "file":
                    file_id = self.node(e.id, "file", e.name, e.provenance, {"assign": e.attributes.get("assign")})
                    self.edge(f"declares>{e.id}", home, file_id, "declares", e.provenance)
                case "exec-sql":
                    for table, mode in sql_tables(e.attributes["text"]):
                        table_id = self.node(f"table:{table}", "table", table, e.provenance)
                        self.edge(f"{e.id}>{mode}>{table}", src, table_id, f"{mode}-table", e.provenance)
                case "exec-cics":
                    self.add_cics(program, e, src)
                case "data" if e.name != "FILLER":
                    self.node(e.id, "data", e.name, e.provenance,
                              {k: v for k, v in e.attributes.items() if k in ("level", "section", "parent", "picture")})
                case "flow":
                    self.add_flow(program, e)

    # PURPOSE: ADDS A FLOWS-TO EDGE FROM EACH FIELD OR FILE A STATEMENT READS TO EACH FIELD IT WRITES
    def add_flow(self, program: str, e: Entity) -> None:
        sources = [self.data_item(program, ref) + (ref,) for ref in e.attributes["sources"]]
        if "file" in e.attributes:
            file_id = f"file:{program}.{e.attributes['file']}"
            known = any(f.id == file_id for f in self.facts[program])
            sources.append((file_id if known else None, "no such file", e.attributes["file"]))
        targets = [self.data_item(program, ref) + (ref,) for ref in e.attributes["targets"]]
        extra = {"verb": e.attributes["verb"]} | ({"corresponding": True} if e.attributes.get("corresponding") else {})
        for src, src_problem, src_ref in sources:
            for dst, dst_problem, dst_ref in targets:
                key = f"{e.id}>{src_ref}>{dst_ref}"
                if src and dst:
                    self.edge(key, src, dst, "flows-to", e.provenance, **extra)
                    continue
                src = src or self.node(f"unresolved:data:{src_ref}", "unresolved", src_ref, e.provenance)
                dst = dst or self.node(f"unresolved:data:{dst_ref}", "unresolved", dst_ref, e.provenance)
                self.edges[key] = Edge(key=key, src=src, dst=dst, kind="flows-to", provenance=e.provenance,
                                       resolved=False, attributes={"reason": src_problem or dst_problem} | extra)

    # PURPOSE: ADDS A PERFORM OR GO TO EDGE, WITH THE THRU END RESOLVED TOO
    def add_jump(self, program: str, e: Entity, src: str) -> None:
        kind = "performs" if e.kind == "perform" else "goes-to"
        section = e.attributes.get("in_section")
        target = self.procedure(program, e.attributes["target"], e.attributes.get("paragraph"), section)
        if target is None:
            self.unresolved(e.id, src, f"paragraph:{e.attributes['target']}", kind, e.provenance,
                            "no such paragraph or section")
            return
        extra = {}
        if "thru" in e.attributes:
            extra["thru"] = self.procedure(program, e.attributes["thru"], e.attributes.get("paragraph"), section) \
                or e.attributes["thru"]
        self.edge(e.id, src, target, kind, e.provenance, **extra)

    # PURPOSE: ADDS A CALL EDGE TO ANOTHER PROGRAM, OR AN UNRESOLVED ONE WITH ITS REASON
    def add_call(self, program: str, e: Entity, src: str) -> None:
        target = e.attributes["target"]
        if e.attributes["dynamic"] and "target_from" not in e.attributes:
            self.add_dynamic(program, e, src, target, "call")
        else:
            self.call_edge(e.id, src, target, e.provenance, "call")

    # PURPOSE: ADDS ONE CALL EDGE PER LITERAL THE TARGET DATA ITEM CAN HOLD, OR AN UNRESOLVED EDGE IF NONE
    def add_dynamic(self, program: str, e: Entity, src: str, data_name: str, via: str) -> None:
        candidates = self.values_of(program, data_name)
        if not candidates:
            self.unresolved(e.id, src, f"dynamic:{data_name}", "calls", e.provenance,
                            "dynamic target with no VALUE or MOVE of a literal", via=via)
        for value, fact in candidates:
            key = e.id if len(candidates) == 1 else f"{e.id}>{value}"
            self.call_edge(key, src, value, e.provenance, via, target_from=fact)

    # PURPOSE: ADDS A CALLS EDGE, OR AN UNRESOLVED ONE WHEN THE PROGRAM IS NOT IN THE ANALYZED CODE
    def call_edge(self, key: str, src: str, target: str, where: Provenance, via: str, **extra) -> None:
        if target in self.programs:
            self.edge(key, src, f"program:{target}", "calls", where, via=via, **extra)
        else:
            self.unresolved(key, src, f"program:{target}", "calls", where, "program not in the analyzed code",
                            via=via, **extra)

    # PURPOSE: ADDS AN INCLUDES EDGE FROM THE PROGRAM TO THE COPYBOOK IT COPIES
    def add_copybook(self, e: Entity, home: str) -> None:
        resolved = e.attributes["resolved"]
        if resolved is None:
            self.unresolved(e.id, home, f"copybook:{e.name}", "includes", e.provenance, e.attributes["problem"])
            return
        book = self.node(f"copybook:{e.name}", "copybook", e.name, Provenance(file=resolved, line=1),
                         {"path": resolved})
        extra = {"problem": e.attributes["problem"]} if e.attributes["problem"] else {}
        self.edge(e.id, home, book, "includes", e.provenance, **extra)

    # PURPOSE: ADDS CICS LINK/XCTL CALL EDGES AND CICS FILE ACCESS EDGES
    def add_cics(self, program: str, e: Entity, src: str) -> None:
        command = e.attributes["command"]
        if command in ("LINK", "XCTL"):
            via = f"cics-{command.lower()}"
            if "program" in e.attributes:
                self.call_edge(e.id, src, e.attributes["program"], e.provenance, via)
            elif "program_ref" in e.attributes:
                self.add_dynamic(program, e, src, e.attributes["program_ref"], via)
        elif command in CICS_FILE_COMMANDS and ("file" in e.attributes or "file_ref" in e.attributes):
            names = [(e.attributes["file"], None)] if "file" in e.attributes \
                else self.values_of(program, e.attributes["file_ref"])
            if not names:
                self.unresolved(e.id, src, f"dynamic:{e.attributes['file_ref']}", "cics-file", e.provenance,
                                "dynamic target with no VALUE or MOVE of a literal", command=command)
            for name, fact in names:
                file_id = self.node(f"cics-file:{name}", "cics-file", name, e.provenance)
                key = e.id if len(names) == 1 else f"{e.id}>{name}"
                extra = {"target_from": fact} if fact else {}
                self.edge(key, src, file_id, "cics-file", e.provenance, command=command, **extra)

    # PURPOSE: ADDS JOB, STEP, PROGRAM, PROC AND DATASET EDGES, AND BINDS PROGRAM FILES TO DATASETS
    def add_job(self, job: JclJob, procs: set[str]) -> None:
        job_id = self.node(f"{job.kind.lower()}:{job.name}", job.kind.lower(), job.name, job.provenance)
        for step in job.steps:
            step_id = self.node(f"step:{job.name}.{step.name}", "step", step.name, step.provenance)
            self.edge(f"contains>{step_id}", job_id, step_id, "contains", step.provenance)
            if step.program:
                if step.program in self.programs:
                    self.edge(f"runs>{step_id}", step_id, f"program:{step.program}", "runs", step.provenance)
                else:
                    self.unresolved(f"runs>{step_id}", step_id, f"program:{step.program}", "runs", step.provenance,
                                    "program not in the analyzed code")
            elif step.proc:
                if step.proc in procs:
                    self.edge(f"runs>{step_id}", step_id, f"proc:{step.proc}", "runs-proc", step.provenance)
                else:
                    self.unresolved(f"runs>{step_id}", step_id, f"proc:{step.proc}", "runs-proc", step.provenance,
                                    "procedure not in the analyzed code")
            files = {  # RENAME: DD NAME TO THE FILE ENTITY THE STEP'S PROGRAM ASSIGNS TO IT
                DD_PREFIX_RE.sub("", (f.attributes.get("assign") or "").upper()): f.id
                for f in self.facts.get(step.program or "", []) if f.kind == "file"
            }
            for dd in step.dds:
                if dd.dataset is None:
                    continue
                dataset = self.node(f"dataset:{dd.dataset}", "dataset", dd.dataset, dd.provenance)
                self.edge(f"dd>{step_id}>{dd.name}", step_id, dataset, "dd", dd.provenance, ddname=dd.name, disp=dd.disp)
                if dd.name in files:
                    self.edge(f"binds>{step_id}>{dd.name}", files[dd.name], dataset, "binds", dd.provenance,
                              step=step_id, ddname=dd.name)

    # PURPOSE: COPIES EACH COMPONENT'S CONFIG ONTO THE PROGRAM NODES UNDER ITS PATH
    def add_components(self, config: Config) -> None:
        for component in config.components:
            prefix = component.path.rstrip("/") + "/"
            meta = {"id": component.id, "criticality": str(component.criticality),
                    "data_stores": component.data_stores, "relied_on_by": component.relied_on_by}
            for node_id, node in self.nodes.items():
                if node.kind == "program" and node.provenance.file.startswith(prefix):
                    self.nodes[node_id] = node.model_copy(update={"attributes": node.attributes | {"component": meta}})

    # PURPOSE: RETURNS THE FINISHED GRAPH, NODES AND EDGES IN A STABLE ORDER
    def graph(self) -> Graph:
        return Graph(nodes=sorted(self.nodes.values(), key=lambda n: n.id),
                     edges=sorted(self.edges.values(), key=lambda e: e.key))


# PURPOSE: BUILDS A GRAPH FROM ALREADY-PARSED MODULES AND JCL
def graph_from(modules: list[IRModule], jobs: list[JclJob], config: Config | None = None) -> Graph:
    builder = GraphBuilder()
    builder.index(modules)
    for program in sorted(builder.programs):
        builder.add_program(program)
    procs = {j.name for j in jobs if j.kind == "PROC"}
    for job in jobs:
        builder.add_job(job, procs)
    if config:
        builder.add_components(config)
    return builder.graph()


# PURPOSE: PARSES COBOL PROGRAMS AND JCL UNDER ROOT, THEN BUILDS THEIR GRAPH
def build_graph(root: Path, programs: list[str], copybook_dirs: list[str], jcl: list[str] = (),
                config: Config | None = None) -> Graph:
    adapter = CobolAdapter(copybook_dirs)
    modules = [adapter.parse(Path(root) / p, Path(root)) for p in programs]
    jobs = [job for path in jcl for job in parse_jcl(Path(root) / path, Path(root))]
    return graph_from(modules, jobs, config)
