from typing import Any

import networkx as nx
from pydantic import BaseModel, ConfigDict, Field

from changeproof.provenance import Provenance


class Node(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)
    kind: str
    name: str
    provenance: Provenance  # where the thing is defined, or first referenced when it is defined elsewhere
    attributes: dict[str, Any] = {}


class Edge(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    key: str = Field(min_length=1)  # the IR fact or JCL statement the edge came from, unique per graph
    src: str
    dst: str
    kind: str
    provenance: Provenance
    resolved: bool = True
    attributes: dict[str, Any] = {}


class Graph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nodes: list[Node] = []
    edges: list[Edge] = []

    # PURPOSE: EDGES WHOSE TARGET IS NOT IN THE ANALYZED CODE, WITH THE REASON
    @property
    def unresolved(self) -> list[Edge]:
        return [e for e in self.edges if not e.resolved]

    # PURPOSE: RETURNS A NETWORKX MULTIDIGRAPH VIEW FOR QUERIES AND TRAVERSALS
    def to_networkx(self) -> nx.MultiDiGraph:
        g = nx.MultiDiGraph()
        for n in self.nodes:
            g.add_node(n.id, kind=n.kind, name=n.name, provenance=str(n.provenance), **n.attributes)
        for e in self.edges:
            g.add_edge(e.src, e.dst, key=e.key, kind=e.kind, provenance=str(e.provenance), resolved=e.resolved,
                       **e.attributes)
        return g
