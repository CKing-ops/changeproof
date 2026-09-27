"""Stores a graph in SQLite so later weeks can query it without re-parsing."""

import json
import sqlite3
from pathlib import Path

from changeproof.graph.model import Edge, Graph, Node

SCHEMA = """
CREATE TABLE nodes (id TEXT PRIMARY KEY, kind TEXT NOT NULL, name TEXT NOT NULL,
                    file TEXT NOT NULL, line INTEGER NOT NULL, end_line INTEGER, attributes TEXT NOT NULL);
CREATE TABLE edges (key TEXT PRIMARY KEY, src TEXT NOT NULL REFERENCES nodes(id), dst TEXT NOT NULL REFERENCES nodes(id),
                    kind TEXT NOT NULL, file TEXT NOT NULL, line INTEGER NOT NULL, end_line INTEGER,
                    resolved INTEGER NOT NULL, attributes TEXT NOT NULL);
CREATE INDEX edges_src ON edges(src);
CREATE INDEX edges_dst ON edges(dst);
"""


# PURPOSE: WRITES A GRAPH TO A NEW SQLITE FILE, REPLACING ANY OLD ONE
def save_graph(graph: Graph, path: Path) -> None:
    Path(path).unlink(missing_ok=True)
    with sqlite3.connect(path) as db:
        db.executescript(SCHEMA)
        db.executemany("INSERT INTO nodes VALUES (?, ?, ?, ?, ?, ?, ?)", [
            (n.id, n.kind, n.name, n.provenance.file, n.provenance.line, n.provenance.end_line,
             json.dumps(n.attributes, sort_keys=True)) for n in graph.nodes
        ])
        db.executemany("INSERT INTO edges VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", [
            (e.key, e.src, e.dst, e.kind, e.provenance.file, e.provenance.line, e.provenance.end_line,
             int(e.resolved), json.dumps(e.attributes, sort_keys=True)) for e in graph.edges
        ])
    db.close()


# PURPOSE: READS A GRAPH BACK FROM SQLITE
def load_graph(path: Path) -> Graph:
    with sqlite3.connect(path) as db:
        nodes = [
            Node(id=i, kind=k, name=n, provenance={"file": f, "line": ln, "end_line": end}, attributes=json.loads(a))
            for i, k, n, f, ln, end, a in db.execute("SELECT * FROM nodes ORDER BY id")
        ]
        edges = [
            Edge(key=key, src=s, dst=d, kind=k, provenance={"file": f, "line": ln, "end_line": end},
                 resolved=bool(r), attributes=json.loads(a))
            for key, s, d, k, f, ln, end, r, a in db.execute("SELECT * FROM edges ORDER BY key")
        ]
    db.close()
    return Graph(nodes=nodes, edges=edges)
