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

    # PURPOSE: VALUE LITERAL OF A DATA ITEM, SO A DATA-NAME TARGET CAN BE RESOLVED STATICALLY
    def value_of(self, program: str, data_name: str) -> str | None:
        return next((e.attributes["value"].strip().upper() for e in self.facts[program]
                     if e.kind == "data" and e.name == data_name and "value" in e.attributes), None)

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
        target, via = e.attributes["target"], "call"
        if e.attributes["dynamic"] and "target_from" not in e.attributes:
            self.unresolved(e.id, src, f"dynamic:{target}", "calls", e.provenance, "dynamic target with no VALUE", via=via)
        elif target in self.programs:
            self.edge(e.id, src, f"program:{target}", "calls", e.provenance, via=via)
        else:
            self.unresolved(e.id, src, f"program:{target}", "calls", e.provenance, "program not in the analyzed code",
                            via=via)

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
            target = e.attributes.get("program") or self.value_of(program, e.attributes.get("program_ref", ""))
            via = f"cics-{command.lower()}"
            if target is None:
                self.unresolved(e.id, src, f"dynamic:{e.attributes.get('program_ref')}", "calls", e.provenance,
                                "dynamic target with no VALUE", via=via)
            elif target in self.programs:
                self.edge(e.id, src, f"program:{target}", "calls", e.provenance, via=via)
            else:
                self.unresolved(e.id, src, f"program:{target}", "calls", e.provenance,
                                "program not in the analyzed code", via=via)
        elif command in CICS_FILE_COMMANDS and ("file" in e.attributes or "file_ref" in e.attributes):
            name = e.attributes.get("file") or self.value_of(program, e.attributes["file_ref"])
            if name is None:
                self.unresolved(e.id, src, f"dynamic:{e.attributes['file_ref']}", "cics-file", e.provenance,
                                "dynamic target with no VALUE", command=command)
                return
            file_id = self.node(f"cics-file:{name}", "cics-file", name, e.provenance)
            self.edge(e.id, src, file_id, "cics-file", e.provenance, command=command)

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
