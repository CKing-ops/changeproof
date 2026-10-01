"""Impact walk over the dependency graph (ROADMAP Week 5).

From each changed entity the walk follows dependencies backwards (who calls, performs, copies or runs
this?) and data forwards (who reads what this writes?). Every step it takes is a graph edge, or a
containment fact, with its provenance, so each impacted entity comes with the path that reached it.

Confidence tiers:
- definite: reached only through static dependencies (contains, PERFORM, CALL of a literal, COPY,
  EXEC PGM, CSD PROGRAM) or the use of a changed data definition;
- probable: the path includes a dynamic target resolved through a moved literal, a data value
  flowing to a reader, or a step whose input changed;
- possible: the path goes through a shared table, CICS file or dataset that an impacted entity writes.
"""

import heapq
from dataclasses import dataclass
from enum import IntEnum

from changeproof.adapters.base import ChangeKind, EntityChange
from changeproof.graph.build import find_data
from changeproof.graph.lineage import hierarchy
from changeproof.graph.model import Edge, Graph
from changeproof.provenance import Provenance


class Tier(IntEnum):
    DEFINITE = 0
    PROBABLE = 1
    POSSIBLE = 2


@dataclass(frozen=True)
class Step:
    src: str
    dst: str
    edge: str
    provenance: Provenance


@dataclass(frozen=True)
class Reached:
    tier: Tier
    via: tuple[Step, ...]


STATIC_KINDS = {  # RENAME: EDGES WALKED FROM TARGET BACK TO SOURCE, WITH THE NAME OF THAT STEP
    "contains": "contained-in", "performs": "performed-by", "goes-to": "gone-to-from", "calls": "called-by",
    "includes": "included-by", "declares": "declared-by", "runs": "run-by", "runs-proc": "run-by",
    "starts": "started-by", "uses-screen": "screen-of",
}
CICS_READS = frozenset({"READ", "READNEXT", "READPREV", "STARTBR"})  # RENAME: CICS FILE COMMANDS THAT READ
CICS_WRITES = frozenset({"WRITE", "REWRITE", "DELETE"})  # RENAME: CICS FILE COMMANDS THAT WRITE
DD_WRITES = frozenset({"NEW", "MOD", "OLD"})  # RENAME: DISP STATUSES UNDER WHICH A STEP MAY WRITE THE DATASET
DD_READS = frozenset({"SHR", "OLD"})  # RENAME: DISP STATUSES UNDER WHICH A STEP READS THE DATASET


# PURPOSE: THE DISP STATUS OF A DD; JCL TREATS A MISSING DISP AS NEW
def disp_status(edge: Edge) -> str:
    return (edge.attributes.get("disp") or "NEW").strip("()").split(",")[0].upper() or "NEW"


# PURPOSE: THE PROGRAM NAME AN IR ENTITY ID BELONGS TO
def program_of(entity_id: str) -> str:
    return entity_id.split(":", 1)[1].split(".", 1)[0].split("#", 1)[0]


class ImpactWalk:
    # PURPOSE: INDEXES THE GRAPH ONCE FOR EVERY WALK
    def __init__(self, graph: Graph) -> None:
        self.nodes = {n.id: n for n in graph.nodes}
        self.into: dict[str, list[Edge]] = {}
        self.out: dict[str, list[Edge]] = {}
        for e in graph.edges:
            self.into.setdefault(e.dst, []).append(e)
            self.out.setdefault(e.src, []).append(e)
        self.ancestors, self.descendants = hierarchy(graph)
        self.data = [(n.id, n.name) for n in graph.nodes if n.kind == "data"]
        self.writers = {e.src for e in graph.edges if e.kind == "writes-table"
                        or e.kind == "cics-file" and e.attributes["command"] in CICS_WRITES}

    # PURPOSE: WHERE A CHANGED ENTITY ENTERS THE GRAPH, AS (NODE, MODE, STEP FROM THE ENTITY OR NONE IF IT IS THE NODE)
    def anchors(self, change: EntityChange) -> list[tuple[str, str, Step | None]]:
        e = change.entity
        found: list[tuple[str, str, Step | None]] = []
        if e.kind in ("jcl-step", "jcl-dd"):
            scope = e.id.split(":", 1)[1]
            step = "step:" + (scope.rsplit(".", 1)[0] if e.kind == "jcl-dd" else scope)
            jobs = [f"{kind}:{scope.split('.', 1)[0]}" for kind in ("job", "proc")]
            node = next((n for n in [step, *jobs] if n in self.nodes), None)
            if node is None:
                return []
            return [(node, "node", None if node == step and e.kind == "jcl-step" else
                     Step(e.id, node, "contained-in", e.provenance))]
        if e.id in self.nodes:
            found.append((e.id, "definition" if e.kind == "data" else "node", None))
        if change.change == ChangeKind.REMOVED and (stub := f"unresolved:{e.kind}:{e.name}") in self.nodes:
            found.append((stub, "node", Step(e.id, stub, "removed-but-referenced", e.provenance)))
        if e.kind.startswith("jcl-"):
            return found
        program = f"program:{program_of(e.id)}"
        if e.kind == "condition" and e.attributes["parent"] in self.nodes:
            found.append((e.attributes["parent"], "definition", Step(e.id, e.attributes["parent"], "part-of", e.provenance)))
        if e.kind == "flow" and change.change != ChangeKind.REMOVED:
            for ref in e.attributes["targets"]:
                if (item := find_data(self.data, program_of(e.id), ref)[0]) is not None:
                    found.append((item, "value", Step(e.id, item, "writes", e.provenance)))
        paragraph = e.attributes.get("paragraph")
        if paragraph in self.nodes and paragraph != e.id:
            found.append((paragraph, "node", Step(e.id, paragraph, "contained-in", e.provenance)))
        if program in self.nodes and program != e.id:
            found.append((program, "node", Step(e.id, program, "contained-in", e.provenance)))
        return found

    # PURPOSE: EVERY NODE ONE STEP FURTHER, AS (NODE, MODE, TIER OF THE STEP, STEP)
    def neighbours(self, node: str, mode: str) -> list[tuple[str, str, Tier, Step]]:
        kind = self.nodes[node].kind
        found = []
        for e in self.into.get(node, []):
            if e.kind in STATIC_KINDS:
                tier = Tier.PROBABLE if "target_from" in e.attributes else Tier.DEFINITE
                found.append((e.src, "node", tier, Step(node, e.src, STATIC_KINDS[e.kind], e.provenance)))
            elif e.kind == "starts-transaction":
                found.append((e.src, "node", Tier.PROBABLE, Step(node, e.src, "started-from", e.provenance)))
            elif e.kind == "reads-table" or e.kind == "cics-file" and e.attributes["command"] in CICS_READS:
                found.append((e.src, "node", Tier.POSSIBLE, Step(node, e.src, "read-by", e.provenance)))
            elif e.kind == "cics-dataset":
                found.append((e.src, "node", Tier.POSSIBLE, Step(node, e.src, "dataset-of", e.provenance)))
            elif e.kind == "dd" and disp_status(e) in DD_READS:
                found.append((e.src, "node", Tier.POSSIBLE, Step(node, e.src, "read-by", e.provenance)))
            elif e.kind == "binds":
                found.append((e.src, "value", Tier.POSSIBLE, Step(node, e.src, "bound-to", e.provenance)))
        for e in self.out.get(node, []):
            if e.kind == "writes-table" or e.kind == "cics-file" and e.attributes["command"] in CICS_WRITES:
                found.append((e.dst, "node", Tier.POSSIBLE, Step(node, e.dst, "writes", e.provenance)))
            elif e.kind == "cics-dataset":
                found.append((e.dst, "node", Tier.POSSIBLE, Step(node, e.dst, "dataset", e.provenance)))
            elif e.kind == "dd" and disp_status(e) in DD_WRITES:
                found.append((e.dst, "node", Tier.POSSIBLE, Step(node, e.dst, "writes", e.provenance)))
            elif e.kind == "runs":
                found.append((e.dst, "node", Tier.PROBABLE, Step(node, e.dst, "runs", e.provenance)))
            elif e.kind == "contains" and kind == "program" and e.dst in self.writers:
                found.append((e.dst, "node", Tier.POSSIBLE, Step(node, e.dst, "may-change-output-of", e.provenance)))
        if kind in ("data", "file"):
            found += self.data_neighbours(node, mode)
        return found

    # PURPOSE: PARAGRAPHS AND FIELDS A CHANGED DATA DEFINITION OR VALUE REACHES
    def data_neighbours(self, node: str, mode: str) -> list[tuple[str, str, Tier, Step]]:
        found = []
        if mode == "definition":
            for group in self.ancestors.get(node, []):
                found.append((group, "definition", Tier.DEFINITE, Step(node, group, "part-of", self.nodes[node].provenance)))
            uses = [e for e in self.out.get(node, []) + self.into.get(node, []) if e.kind == "flows-to" and e.resolved]
            for e in uses:
                if "paragraph" in e.attributes:
                    found.append((e.attributes["paragraph"], "node", Tier.DEFINITE,
                                  Step(node, e.attributes["paragraph"], "used-by", e.provenance)))
            for e in self.into.get(node, []):
                if e.kind == "uses-data":
                    found.append((e.src, "node", Tier.DEFINITE, Step(node, e.src, "used-by", e.provenance)))
        related = [node, *self.ancestors.get(node, []), *self.descendants.get(node, [])]
        for item in related:
            for e in self.out.get(item, []):
                if e.kind == "flows-to" and e.resolved:
                    found.append((e.dst, "value", Tier.PROBABLE, Step(node, e.dst, "flows-to", e.provenance)))
                    if "paragraph" in e.attributes:
                        found.append((e.attributes["paragraph"], "node", Tier.PROBABLE,
                                      Step(node, e.attributes["paragraph"], "read-by", e.provenance)))
            for e in self.into.get(item, []):
                if e.kind == "uses-data" and e.attributes["mode"] == "read":
                    found.append((e.src, "node", Tier.PROBABLE, Step(node, e.src, "read-by", e.provenance)))
        return found

    # PURPOSE: THE BEST TIER AND SHORTEST PATH TO EVERY NODE THE CHANGES REACH, KEYED BY NODE
    def walk(self, changes: list[EntityChange]) -> tuple[dict[str, Reached], set[str]]:
        queue, seq = [], 0
        changed = {c.entity.id for c in changes}
        for change in changes:
            for node, mode, step in self.anchors(change):
                if step is None:
                    changed.add(node)
                heapq.heappush(queue, (Tier.DEFINITE, 0, seq, node, mode, () if step is None else (step,)))
                seq += 1
        done: dict[tuple[str, str], Reached] = {}
        while queue:
            tier, hops, _, node, mode, via = heapq.heappop(queue)
            if (node, mode) in done:
                continue
            done[(node, mode)] = Reached(Tier(tier), via)
            for other, other_mode, step_tier, step in self.neighbours(node, mode):
                if (other, other_mode) not in done:
                    seq += 1
                    heapq.heappush(queue, (max(tier, step_tier), hops + 1, seq, other, other_mode, via + (step,)))
        best: dict[str, Reached] = {}
        for (node, _), reached in done.items():
            if node not in best or (reached.tier, len(reached.via)) < (best[node].tier, len(best[node].via)):
                best[node] = reached
        return best, changed
