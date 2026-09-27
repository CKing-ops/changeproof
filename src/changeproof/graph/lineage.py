"""Field-level lineage over flows-to edges (ROADMAP Week 4).

Writing a group writes every field inside it, and writing a field changes the group that holds it,
so each step also looks at the field's enclosing groups and its subordinate fields. The result is
what may flow, not what must: REDEFINES and conditional paths are not narrowed.
"""

from collections import deque

from changeproof.graph.model import Edge, Graph


# PURPOSE: MAPS EACH DATA ITEM TO ITS ENCLOSING GROUPS AND TO ITS SUBORDINATE FIELDS
def hierarchy(graph: Graph) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    parent = {n.id: n.attributes["parent"] for n in graph.nodes if n.kind == "data" and "parent" in n.attributes}
    children: dict[str, list[str]] = {}
    for child, group in parent.items():
        children.setdefault(group, []).append(child)
    ancestors = {}
    for node_id in parent:
        chain, current = [], node_id
        while current in parent:
            current = parent[current]
            chain.append(current)
        ancestors[node_id] = chain
    descendants = {}
    for group in children:
        found, stack = [], list(children[group])
        while stack:
            item = stack.pop()
            found.append(item)
            stack.extend(children.get(item, []))
        descendants[group] = found
    return ancestors, descendants


# PURPOSE: WALKS FLOWS-TO EDGES ONE WAY AND RETURNS EACH NODE REACHED WITH THE EDGE THAT FIRST REACHED IT
def walk(graph: Graph, start: str, upstream: bool) -> dict[str, Edge]:
    ancestors, descendants = hierarchy(graph)
    step: dict[str, list[Edge]] = {}  # RENAME: NODE TO THE FLOWS-TO EDGES LEAVING IT IN THE WALK DIRECTION
    for e in graph.edges:
        if e.kind == "flows-to" and e.resolved:
            step.setdefault(e.dst if upstream else e.src, []).append(e)
    reached: dict[str, Edge] = {}
    queue = deque([start])
    seen = {start}
    while queue:
        node = queue.popleft()
        for related in [node, *ancestors.get(node, []), *descendants.get(node, [])]:
            for e in step.get(related, []):
                other = e.src if upstream else e.dst
                if other not in seen:
                    seen.add(other)
                    reached[other] = e
                    queue.append(other)
    return reached


# PURPOSE: FIELDS AND FILES WHOSE DATA MAY FLOW INTO A NODE
def upstream(graph: Graph, node_id: str) -> dict[str, Edge]:
    return walk(graph, node_id, upstream=True)


# PURPOSE: FIELDS WHOSE DATA A NODE MAY FLOW INTO
def downstream(graph: Graph, node_id: str) -> dict[str, Edge]:
    return walk(graph, node_id, upstream=False)
