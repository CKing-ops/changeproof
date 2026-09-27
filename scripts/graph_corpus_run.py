"""Builds the CardDemo dependency graph, with field-level data flow, and checks every edge (Weeks 3 and 4).

    uv run python scripts/graph_corpus_run.py

Writes docs/weekly/week04-carddemo-graph.json (counts and problems) and, git-ignored,
corpus/carddemo-graph.sqlite for querying.
"""

import json
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from changeproof.adapters.cobol import CobolAdapter
from changeproof.graph import graph_from, save_graph
from changeproof.graph.check import check_edges
from changeproof.config import load_config
from changeproof.graph.csd import parse_csd
from changeproof.graph.jcl import parse_jcl

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "carddemo"
COPYBOOK_DIRS = sorted(  # RENAME: CARDDEMO FOLDERS SEARCHED FOR COPYBOOKS AND DCLGEN MEMBERS
    p.relative_to(CORPUS).as_posix() for p in CORPUS.glob("app/**/*") if p.is_dir() and p.name in ("cpy", "cpy-bms", "dcl")
)
CONFIG = ROOT / "docs" / "examples" / "carddemo.yaml"  # RENAME: COMPONENT LAYOUT USED FOR CARDDEMO
REPORT = ROOT / "docs" / "weekly" / "week04-carddemo-graph.json"
DATABASE = ROOT / "corpus" / "carddemo-graph.sqlite"


# PURPOSE: PARSES ONE PROGRAM IN A WORKER PROCESS
def parse_one(path: Path):
    return CobolAdapter(COPYBOOK_DIRS).parse(path, CORPUS)


# PURPOSE: BUILDS, CHECKS AND STORES THE GRAPH, THEN WRITES THE SUMMARY
def main() -> int:
    programs = sorted(p for p in CORPUS.glob("app/**/*") if p.suffix.lower() == ".cbl")
    jcl = sorted(p for p in CORPUS.glob("app/**/*") if p.suffix.lower() in (".jcl", ".prc"))
    csd = sorted(p for p in CORPUS.glob("app/**/*") if p.suffix.lower() == ".csd")
    with ProcessPoolExecutor() as pool:
        modules = list(pool.map(parse_one, programs))
    jobs = [job for path in jcl for job in parse_jcl(path, CORPUS)]
    definitions = [d for path in csd for d in parse_csd(path, CORPUS)]
    graph = graph_from(modules, jobs, load_config(CONFIG), definitions)
    problems = check_edges(graph, CORPUS)
    save_graph(graph, DATABASE)
    summary = {
        "programs": len(modules),
        "jcl_members": len(jcl),
        "csd_members": len(csd),
        "nodes": dict(sorted(Counter(n.kind for n in graph.nodes).items())),
        "edges": dict(sorted(Counter(e.kind for e in graph.edges).items())),
        "edges_total": len(graph.edges),
        "edges_with_provenance": sum(1 for e in graph.edges if e.provenance.file and e.provenance.line),
        "edges_failing_check": problems,
        "edges_crossing_components": dict(sorted(Counter(
            f"{e.kind}: {' -> '.join(e.attributes['crosses'])}" for e in graph.edges if "crosses" in e.attributes
        ).items())),
        "shared_resources": {n.id: n.attributes["shared_by"] for n in graph.nodes if "shared_by" in n.attributes},
        "unresolved": dict(sorted(Counter(f"{e.kind}: {e.attributes['reason']}" for e in graph.unresolved).items())),
        "unresolved_examples": [f"{e.src} -{e.kind}-> {e.dst} at {e.provenance}" for e in graph.unresolved[:25]],
    }
    REPORT.write_text(json.dumps(summary, indent=1) + "\n")
    print(json.dumps({k: v for k, v in summary.items() if k != "unresolved_examples"}, indent=1))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
