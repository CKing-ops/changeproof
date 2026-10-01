"""Checks that each edge's provenance points at the statement that produced it (Week 3 exit check).

An edge passes when its cited lines exist and contain the word that makes the edge: PERFORM for a
perform, the table name for a table access, the DD name for a JCL binding, and so on.
"""

from functools import cache
from pathlib import Path

from changeproof.graph.model import Edge, Graph


# PURPOSE: WORDS OF WHICH AT LEAST ONE MUST APPEAR IN THE LINES AN EDGE CITES
def anchors(edge: Edge, names: dict[str, str]) -> list[str]:
    match edge.kind:
        case "contains":
            return ["EXEC"] if edge.dst.startswith("step:") else [names[edge.dst]]
        case "performs":
            return ["PERFORM"]
        case "goes-to":
            return ["GO"]
        case "calls":
            return ["CALL"] if edge.attributes.get("via") == "call" else ["LINK", "XCTL"]
        case "uses-crypto":
            return ["CALL"] if edge.attributes["via"] == "call" else [names[edge.dst]]
        case "includes":
            return ["COPY", "INCLUDE"]
        case "declares":
            return ["SELECT"]
        case "reads-table" | "writes-table":
            return [names[edge.dst].rsplit(".", 1)[-1]]
        case "cics-file":
            return [edge.attributes["command"]]
        case "runs" | "runs-proc":
            return ["EXEC"]
        case "flows-to":
            return [edge.attributes["verb"]]
        case "uses-data":
            return [edge.attributes["ref"].split()[0].rsplit(".", 1)[-1]]
        case "starts" | "cics-dataset":
            return [names[edge.dst]]
        case "uses-screen":
            return [edge.attributes["command"]]
        case "starts-transaction":
            return ["TRANSID"]
        case "dd" | "binds":
            return [f"//{edge.attributes['ddname']}"]
    return []


# PURPOSE: RETURNS ONE PROBLEM PER EDGE WHOSE CITED LINES ARE MISSING OR DO NOT HOLD ITS STATEMENT
def check_edges(graph: Graph, root: Path) -> list[str]:
    names = {n.id: n.name for n in graph.nodes}

    # PURPOSE: READS A SOURCE FILE ONCE, UPPERCASED
    @cache
    def lines_of(file: str) -> tuple[str, ...]:
        return tuple((Path(root) / file).read_text(encoding="latin-1").upper().splitlines())

    problems = []
    for edge in graph.edges:
        where = edge.provenance
        lines = lines_of(where.file)
        last = where.end_line or where.line
        if last > len(lines):
            problems.append(f"{edge.key}: {where} is past the end of the file")
            continue
        text = "\n".join(lines[where.line - 1:last])
        words = anchors(edge, names)
        if not words or not any(w.upper() in text for w in words):
            problems.append(f"{edge.key}: {where} does not contain {' or '.join(words) or 'a known anchor'}")
    return problems
