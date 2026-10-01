"""Week 11 exit check: impact on an open-source Java project, Apache Commons Lang.

    uv run python scripts/fetch_java_corpus.py      # once, setup-time network
    uv run python scripts/java_impact_check.py

Runs `impact` on every commit in the fetched window that changes main Java sources and has its
parent fetched. For each it checks that every changed entity lies in a changed hunk of its file
(so no change is invented), and it records counts and timing. It also builds the graph of the whole
project at the pinned head and runs the Week 3 provenance check on every edge. Writes
docs/weekly/week11-java-impact.json.
"""

import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

from changeproof.change.git import tree_diffs
from changeproof.graph.check import check_edges
from changeproof.impact.run import run_impact, system_graph

ROOT = Path(__file__).resolve().parent.parent
CORPUS = ROOT / "corpus" / "java" / "commons-lang"
REPORT = ROOT / "docs" / "weekly" / "week11-java-impact.json"


# PURPOSE: RUNS GIT IN THE CORPUS CHECKOUT
def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(CORPUS), *args], capture_output=True, text=True).stdout.strip()


# PURPOSE: COMMITS THAT CHANGE MAIN JAVA SOURCES AND WHOSE PARENT IS IN THE FETCHED HISTORY, OLDEST FIRST
def commits() -> list[str]:
    shallow = set((CORPUS / ".git" / "shallow").read_text().split()) if (CORPUS / ".git" / "shallow").exists() else set()
    found = git("rev-list", "--reverse", "--no-merges", "HEAD", "--", "src/main/java").split()
    return [sha for sha in found if sha not in shallow]


# PURPOSE: TRUE WHEN TWO LINE RANGES SHARE A LINE
def overlaps(a, b) -> bool:
    return a.line <= (b.end_line or b.line) and b.line <= (a.end_line or a.line)


# PURPOSE: CHANGED ENTITIES THAT LIE IN NO CHANGED HUNK OF THEIR FILE
def outside_hunks(run, base: str, head: str) -> list[str]:
    hunks = {}  # RENAME: FILE TO EVERY CHANGED LINE RANGE ON EITHER SIDE
    for d in tree_diffs(CORPUS, base, head):
        for before, after in d.hunks:
            if before:
                hunks.setdefault(before.file, []).append(before)
            if after:
                hunks.setdefault(after.file, []).append(after)
    where = {c.entity.id: [c.entity.provenance] + ([c.previous.provenance] if c.previous else [])
             for c in run.what.entities}  # RENAME: CHANGED ENTITY ID TO ITS LINE RANGES ON EACH SIDE
    missing = []
    for c in run.what.entities:
        # a fact inside a renamed method or field changes with its container, whose declaration is in a hunk
        sides = where[c.entity.id] + where.get(c.entity.attributes.get("scope"), [])
        if not any(overlaps(s, h) for s in sides for h in hunks.get(s.file, [])):
            missing.append(c.entity.id)
    return missing


# PURPOSE: RUNS IMPACT ON EACH COMMIT, CHECKS THE HEAD GRAPH, AND WRITES THE REPORT
def main() -> int:
    if not (CORPUS / ".git").is_dir():
        print("run scripts/fetch_java_corpus.py first", file=sys.stderr)
        return 2
    rows = []
    for sha in commits():
        start = time.perf_counter()
        run = run_impact(CORPUS, sha)
        seconds = round(time.perf_counter() - start, 1)
        p = run.predicate
        java_files = [f for f in git("diff-tree", "--no-commit-id", "--name-only", "-r", sha).split()
                      if f.endswith(".java")]
        rows.append({"commit": sha, "subject": git("log", "-1", "--format=%s", sha), "java_files": len(java_files),
                     "changed": dict(Counter(c["kind"] for c in p["changed"])),
                     "impacted": dict(Counter(i["confidence"] for i in p["impacted"])),
                     "touches_crypto": p["touches_crypto"], "unresolved": len(p["unresolved"]),
                     "outside_hunks": outside_hunks(run, p["change"]["base"], sha),
                     "problems": run.what.problems, "seconds": seconds})
        print(f"{sha[:7]} changed {sum(rows[-1]['changed'].values())} impacted {len(p['impacted'])} "
              f"in {seconds}s  {rows[-1]['subject'][:60]}")
    graph, failed = system_graph(CORPUS, [], None)
    calls = Counter(e.resolved for e in graph.edges if e.kind == "calls")
    report = {
        "project": "apache/commons-lang", "head": git("rev-parse", "HEAD"), "license": "Apache-2.0",
        "commits": len(rows), "parse_failures": failed,
        "graph": {"nodes": len(graph.nodes), "edges": len(graph.edges), "edge_kinds": dict(Counter(e.kind for e in graph.edges)),
                  "calls_resolved": calls[True], "calls_unresolved": calls[False],
                  "provenance_problems": check_edges(graph, CORPUS)},
        "changes_outside_hunks": sum(len(r["outside_hunks"]) for r in rows),
        "rows": rows,
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"} | {"graph": {k: v for k, v in report["graph"].items()
                                                                                 if k != "provenance_problems"}}, indent=2))
    print("provenance problems:", len(report["graph"]["provenance_problems"]))
    clean = not failed and not report["graph"]["provenance_problems"] and not report["changes_outside_hunks"] \
        and not any(r["problems"] for r in rows)
    return 0 if clean else 1


if __name__ == "__main__":
    sys.exit(main())
