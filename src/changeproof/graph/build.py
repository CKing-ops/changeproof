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
from changeproof.graph.csd import CsdDefinition, parse_csd
from changeproof.graph.jcl import IMS_PROGRAMS, JclJob, parse_jcl
from changeproof.graph.model import Edge, Graph, Node
from changeproof.provenance import Provenance

SQL_WORD_RE = re.compile(r"[\w.$#@:-]+|[(),]")
CICS_FILE_COMMANDS = frozenset({  # RENAME: CICS COMMANDS THAT READ OR WRITE A FILE
    "READ", "WRITE", "REWRITE", "DELETE", "STARTBR", "READNEXT", "READPREV", "ENDBR", "RESETBR", "UNLOCK",
})
SCREEN_COMMANDS = frozenset({"SEND", "RECEIVE"})  # RENAME: CICS COMMANDS THAT SEND OR RECEIVE A BMS MAP
TRANSACTION_COMMANDS = frozenset({"RETURN", "START"})  # RENAME: CICS COMMANDS THAT NAME THE NEXT TRANSACTION
SHARED_KINDS = frozenset({"dataset", "table", "cics-file"})  # RENAME: NODES SEVERAL COMPONENTS CAN SHARE
DD_PREFIX_RE = re.compile(r"^(?:[A-Z]{2}-)*(?:S-)?")  # ASSIGN TO UT-S-NAME style prefixes before the DD name
CICS_DATA_OPTIONS = {  # RENAME: CICS OPTIONS THAT NAME A DATA ITEM, AND WHETHER THE COMMAND READS OR WRITES IT
    "INTO": "write", "SET": "write", "FROM": "read", "RIDFLD": "read", "COMMAREA": "read",
}
CICS_DATA_RE = re.compile(rf"\b({'|'.join(CICS_DATA_OPTIONS)})\s*\(\s*([A-Z0-9][\w-]*(?:\s+(?:OF|IN)\s+[\w-]+)*)\s*\)",
                          re.IGNORECASE)
HOST_VARIABLE_RE = re.compile(r":([A-Z0-9][\w-]*(?:\.[\w-]+)?)", re.IGNORECASE)
SUBSCRIPT_RE = re.compile(r"\s*\([^)]*\)")
REDEFINES_RE = re.compile(r"\bREDEFINES\s+([\w-]+)", re.IGNORECASE)
SQL_TARGET_COMMANDS = frozenset({"SELECT", "FETCH"})  # RENAME: SQL COMMANDS WHOSE INTO LIST IS WRITTEN
SQL_LIST_ENDS = frozenset({"FROM", "WHERE", "SET", "VALUES", "USING", "FOR"})  # RENAME: WORDS THAT END AN INTO LIST


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


# PURPOSE: FINDS THE ONE DATA ITEM IN A PROGRAM THAT A NAME LIKE "FIELD OF GROUP" REFERS TO, OR THE REASON IT CANNOT
def find_data(items: list[tuple[str, str]], program: str, ref: str) -> tuple[str | None, str]:
    name, *qualifiers = re.split(r"\s+(?:OF|IN)\s+", ref.strip().upper())
    matches = [i for i, n in items if n == name and i.startswith(f"data:{program}.")
               and set(qualifiers) <= set(i.split(":", 1)[1].split(".")[1:-1])]
    if len(matches) == 1:
        return matches[0], ""
    return None, f"ambiguous: {len(matches)} data items have this name" if matches else "no such data item"


# PURPOSE: DATA NAMES AN EXEC CICS OR EXEC SQL BLOCK READS OR WRITES, AS (NAME AS WRITTEN, REF, MODE)
def exec_data(kind: str, text: str) -> list[tuple[str, str, str]]:
    if kind == "exec-cics":
        return [(m.group(2), m.group(2), CICS_DATA_OPTIONS[m.group(1).upper()]) for m in CICS_DATA_RE.finditer(text)]
    command = text.split(" ", 1)[0].upper()
    found, mode = [], "read"
    for word in re.findall(r":?[\w.-]+", text):
        upper = word.upper()
        if upper == "INTO" and command in SQL_TARGET_COMMANDS:
            mode = "write"
        elif upper in SQL_LIST_ENDS:
            mode = "read"
        elif m := HOST_VARIABLE_RE.fullmatch(word):
            group, _, field = m.group(1).partition(".")
            found.append((m.group(1), f"{field} OF {group}" if field else group, mode))
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

    # Sources: its VALUE clause, literal MOVEs, MOVEs from other items, and same-picture VALUEs in redefined storage.
    # PURPOSE: LITERALS A DATA ITEM CAN HOLD, AS (VALUE, SOURCE FACT ID)
    def values_of(self, program: str, data_name: str) -> list[tuple[str, str]]:
        found = {}  # RENAME: LITERAL TO THE FIRST FACT THAT PUTS IT IN THE DATA ITEM
        facts = self.facts[program]
        by_id = {e.id: e for e in facts if e.kind == "data"}
        todo, seen = [SUBSCRIPT_RE.sub("", data_name).strip()], set()
        while todo:
            name = todo.pop(0)
            if name in seen:
                continue
            seen.add(name)
            for e in facts:
                if e.kind == "data" and e.name == name:
                    if "value" in e.attributes:
                        found.setdefault(e.attributes["value"].strip().upper(), e.id)
                    for literal, fact in self.redefined_values(e, by_id):
                        found.setdefault(literal, fact)
                elif e.kind == "flow" and any(t.split()[0] == name for t in e.attributes["targets"]):
                    if "literal" in e.attributes:
                        found.setdefault(e.attributes["literal"].strip().upper(), e.id)
                    elif e.attributes["verb"] == "MOVE":
                        todo += [SUBSCRIPT_RE.sub("", src).split()[0] for src in e.attributes["sources"]]
        return list(found.items())

    # PURPOSE: VALUES OF SAME-PICTURE ITEMS INSIDE THE STORAGE THAT AN ENCLOSING GROUP OF THE ITEM REDEFINES
    def redefined_values(self, item: Entity, by_id: dict[str, Entity]) -> list[tuple[str, str]]:
        group = item
        while group is not None and not (m := REDEFINES_RE.search(group.attributes.get("text", ""))):
            group = by_id.get(group.attributes.get("parent"))
        if group is None:
            return []
        prefix = f"{group.id.split('#', 1)[0].rsplit('.', 1)[0]}.{m.group(1).upper()}"
        return [(e.attributes["value"].strip().upper(), e.id) for e in by_id.values()
                if e.id.startswith(prefix + ".") and "value" in e.attributes
                and e.attributes.get("picture") == item.attributes.get("picture")]

    # PURPOSE: FINDS THE DATA ITEM A NAME LIKE "FIELD OF GROUP" REFERS TO, OR THE REASON IT CANNOT
    def data_item(self, program: str, ref: str) -> tuple[str | None, str]:
        return find_data([(e.id, e.name) for e in self.facts[program] if e.kind == "data"], program, ref)

    # PURPOSE: ADDS A USES-DATA EDGE FROM THE PARAGRAPH TO EACH DATA ITEM AN EXEC BLOCK READS OR WRITES
    def add_uses(self, program: str, e: Entity, src: str) -> None:
        for written, ref, mode in exec_data(e.kind, e.attributes["text"]):
            key = f"{e.id}>uses>{written.upper()}>{mode}"
            item, problem = self.data_item(program, ref)
            if item:
                self.edge(key, src, item, "uses-data", e.provenance, mode=mode, ref=written)
            else:
                self.unresolved(key, src, f"data:{written.upper()}", "uses-data", e.provenance, problem,
                                mode=mode, ref=written)

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
                    self.add_uses(program, e, src)
                case "exec-cics":
                    self.add_cics(program, e, src)
                    self.add_uses(program, e, src)
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
        extra = {"verb": e.attributes["verb"]} | ({"corresponding": True} if e.attributes.get("corresponding") else {}) \
            | ({"paragraph": e.attributes["paragraph"]} if "paragraph" in e.attributes else {})
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

    # PURPOSE: ADDS CICS CALL, FILE, SCREEN AND NEXT-TRANSACTION EDGES
    def add_cics(self, program: str, e: Entity, src: str) -> None:
        command = e.attributes["command"]
        if command in ("LINK", "XCTL"):
            via = f"cics-{command.lower()}"
            if "program" in e.attributes:
                self.call_edge(e.id, src, e.attributes["program"], e.provenance, via)
            elif "program_ref" in e.attributes:
                self.add_dynamic(program, e, src, e.attributes["program_ref"], via)
        elif command in CICS_FILE_COMMANDS and ("file" in e.attributes or "file_ref" in e.attributes):
            self.cics_target(program, e, src, "file", "cics-file", "cics-file", command=command)
        elif command in SCREEN_COMMANDS and ("mapset" in e.attributes or "mapset_ref" in e.attributes
                                             or "map" in e.attributes):
            option = "mapset" if "mapset" in e.attributes or "mapset_ref" in e.attributes else "map"
            self.cics_target(program, e, src, option, "mapset", "uses-screen", command=command,
                             map=e.attributes.get("map") or e.attributes.get("map_ref"))
        elif command in TRANSACTION_COMMANDS and ("transid" in e.attributes or "transid_ref" in e.attributes):
            self.cics_target(program, e, src, "transid", "transaction", "starts-transaction", command=command)

    # PURPOSE: LINKS A CICS COMMAND TO THE RESOURCE ITS OPTION NAMES, ONE EDGE PER LITERAL A DATA NAME CAN HOLD
    def cics_target(self, program: str, e: Entity, src: str, option: str, kind: str, edge_kind: str,
                    **attributes) -> None:
        names = [(e.attributes[option], None)] if option in e.attributes \
            else self.values_of(program, e.attributes[f"{option}_ref"])
        if not names:
            self.unresolved(e.id, src, f"dynamic:{e.attributes[f'{option}_ref']}", edge_kind, e.provenance,
                            "dynamic target with no VALUE or MOVE of a literal", **attributes)
        for name, fact in names:
            target = self.node(f"{kind}:{name}", kind, name, e.provenance)
            key = e.id if len(names) == 1 else f"{e.id}>{name}"
            extra = {"target_from": fact} if fact else {}
            self.edge(key, src, target, edge_kind, e.provenance, **attributes, **extra)

    # PURPOSE: ADDS CSD TRANSACTIONS, FILES AND MAPSETS, SO THEIR DEFINITIONS ARE WHERE THE NODES POINT
    def add_csd(self, definitions: list[CsdDefinition]) -> None:
        for d in definitions:
            where = Provenance(file=d.file, line=d.line)
            match d.kind, d.options:
                case "TRANSACTION", {"PROGRAM": (program, _)}:
                    transaction = self.node(f"transaction:{d.name}", "transaction", d.name, where)
                    if program in self.programs:
                        self.edge(f"starts>{transaction}", transaction, f"program:{program}", "starts",
                                  d.through("PROGRAM"))
                    else:
                        self.unresolved(f"starts>{transaction}", transaction, f"program:{program}", "starts",
                                        d.through("PROGRAM"), "program not in the analyzed code")
                case "FILE", _:
                    cics_file = self.node(f"cics-file:{d.name}", "cics-file", d.name, where)
                    if "DSNAME" in d.options:
                        name = d.options["DSNAME"][0]
                        dataset = self.node(f"dataset:{name}", "dataset", name, d.through("DSNAME"))
                        self.edge(f"dsname>{cics_file}", cics_file, dataset, "cics-dataset", d.through("DSNAME"))
                case "MAPSET", _:
                    self.node(f"mapset:{d.name}", "mapset", d.name, where)

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
            for name, where in step.runs:
                via = "ims-region" if step.program in IMS_PROGRAMS else "tso-run"
                if name in self.programs:
                    self.edge(f"runs>{step_id}>{name}", step_id, f"program:{name}", "runs", where, via=via)
                else:
                    self.unresolved(f"runs>{step_id}>{name}", step_id, f"program:{name}", "runs", where,
                                    "program not in the analyzed code", via=via)
            if step.proc and not step.program:
                if step.proc in procs:
                    self.edge(f"runs>{step_id}", step_id, f"proc:{step.proc}", "runs-proc", step.provenance)
                else:
                    self.unresolved(f"runs>{step_id}", step_id, f"proc:{step.proc}", "runs-proc", step.provenance,
                                    "procedure not in the analyzed code")
            files = {  # RENAME: DD NAME TO THE FILE ENTITY THE STEP'S PROGRAM ASSIGNS TO IT
                DD_PREFIX_RE.sub("", (f.attributes.get("assign") or "").upper()): f.id
                for program in [step.program, *(name for name, _ in step.runs)]
                for f in self.facts.get(program or "", []) if f.kind == "file"
            }
            for dd in step.dds:
                if dd.dataset is None:
                    continue
                dataset = self.node(f"dataset:{dd.dataset}", "dataset", dd.dataset, dd.provenance)
                self.edge(f"dd>{step_id}>{dd.name}", step_id, dataset, "dd", dd.provenance, ddname=dd.name, disp=dd.disp)
                if dd.name in files:
                    self.edge(f"binds>{step_id}>{dd.name}", files[dd.name], dataset, "binds", dd.provenance,
                              step=step_id, ddname=dd.name)

    # PURPOSE: COPIES COMPONENT CONFIG ONTO PROGRAM NODES AND MARKS WHERE ONE COMPONENT REACHES ANOTHER
    def add_components(self, config: Config) -> None:
        by_path = sorted(((c.path.rstrip("/") + "/", c) for c in config.components), key=lambda p: -len(p[0]))
        owner = {  # RENAME: NODE ID TO THE COMPONENT ITS DEFINITION LIVES IN, BY LONGEST PATH PREFIX
            node_id: next((c for prefix, c in by_path if node.provenance.file.startswith(prefix)), None)
            for node_id, node in self.nodes.items()
            if node.kind not in SHARED_KINDS and node.kind not in ("unresolved", "crypto-service")
        }
        for node_id, node in self.nodes.items():
            if node.kind == "program" and (c := owner[node_id]):
                meta = {"id": c.id, "criticality": str(c.criticality), "data_stores": c.data_stores,
                        "relied_on_by": c.relied_on_by}
                self.nodes[node_id] = node.model_copy(update={"attributes": node.attributes | {"component": meta}})
        for key, e in self.edges.items():
            a, b = owner.get(e.src), owner.get(e.dst)
            if a and b and a.id != b.id:
                self.edges[key] = e.model_copy(update={"attributes": e.attributes | {"crosses": [a.id, b.id]}})
        for node_id, users in self.users({k: c.id for k, c in owner.items() if c}).items():
            if len(users) > 1:
                node = self.nodes[node_id]
                self.nodes[node_id] = node.model_copy(update={"attributes": node.attributes | {"shared_by": sorted(users)}})

    # PURPOSE: COMPONENTS THAT REACH EACH SHARED RESOURCE, DIRECTLY OR THROUGH ANOTHER RESOURCE
    def users(self, owner: dict[str, str]) -> dict[str, set[str]]:
        incoming: dict[str, list[str]] = {}
        for e in self.edges.values():
            if self.nodes[e.dst].kind in SHARED_KINDS:
                incoming.setdefault(e.dst, []).append(e.src)
        found: dict[str, set[str]] = {}
        for resource in incoming:
            seen, stack, users = {resource}, [resource], set()
            while stack:
                for src in incoming.get(stack.pop(), []):
                    if src in owner:
                        users.add(owner[src])
                    elif src not in seen:
                        seen.add(src)
                        stack.append(src)
            found[resource] = users
        return found

    # PURPOSE: RETURNS THE FINISHED GRAPH, NODES AND EDGES IN A STABLE ORDER
    def graph(self) -> Graph:
        return Graph(nodes=sorted(self.nodes.values(), key=lambda n: n.id),
                     edges=sorted(self.edges.values(), key=lambda e: e.key))


# PURPOSE: BUILDS A GRAPH FROM ALREADY-PARSED MODULES, JCL AND CICS DEFINITIONS
def graph_from(modules: list[IRModule], jobs: list[JclJob], config: Config | None = None,
               csd: list[CsdDefinition] = ()) -> Graph:
    builder = GraphBuilder()
    builder.index(modules)
    builder.add_csd(list(csd))
    for program in sorted(builder.programs):
        builder.add_program(program)
    procs = {j.name for j in jobs if j.kind == "PROC"}
    for job in jobs:
        builder.add_job(job, procs)
    if config:
        builder.add_components(config)
    return builder.graph()


# PURPOSE: PARSES COBOL PROGRAMS, JCL AND CSD EXTRACTS UNDER ROOT, THEN BUILDS THEIR GRAPH
def build_graph(root: Path, programs: list[str], copybook_dirs: list[str], jcl: list[str] = (),
                config: Config | None = None, csd: list[str] = ()) -> Graph:
    adapter = CobolAdapter(copybook_dirs)
    modules = [adapter.parse(Path(root) / p, Path(root)) for p in programs]
    jobs = [job for path in jcl for job in parse_jcl(Path(root) / path, Path(root))]
    definitions = [d for path in csd for d in parse_csd(Path(root) / path, Path(root))]
    return graph_from(modules, jobs, config, definitions)
