"""Impact evidence for a commit or a range of commits (ROADMAP Week 5), as an impact predicate v0.1.

Both sides of the range are checked out from the local repository. The changed entities come from
parsing the changed files on each side; the impact walk runs over the graph of the whole system at
the head, using the changeproof.yaml committed there.
"""

import tempfile
from pathlib import Path, PurePosixPath

import yaml

from changeproof import __version__
from changeproof.adapters.cobol import CobolAdapter
from changeproof.adapters.cobol.parse import CobolSyntaxError
from changeproof.change.git import checkout_tree, commits_in, empty_tree, origin_url, read_commit, tree_diffs
from changeproof.change.message import trailers
from changeproof.change.record import JCL_SUFFIXES, PROGRAM_SUFFIXES, What, what_in, who_of, why_of
from changeproof.config import Config, load_config
from changeproof.graph import graph_from
from changeproof.graph.csd import parse_csd
from changeproof.graph.jcl import parse_jcl
from changeproof.graph.model import Graph
from changeproof.impact.walk import ImpactWalk, Reached
from changeproof.predicates import PREDICATE_TYPES, validate_predicate

CONFIG_NAME = "changeproof.yaml"
CSD_SUFFIXES = frozenset({".csd"})  # RENAME: CICS RESOURCE DEFINITION FILE EXTENSIONS, LOWERCASE
NOT_REPORTED = frozenset({"unresolved", "crypto-service"})  # RENAME: NODE KINDS WALKED THROUGH BUT NEVER LISTED


# PURPOSE: REPO-RELATIVE PATHS IN A TREE WITH ONE OF THE SUFFIXES, SKIPPING COPYBOOK FOLDERS
def files_with(tree: Path, suffixes: frozenset[str], skip: list[str]) -> list[str]:
    found = (p.relative_to(tree).as_posix() for p in tree.rglob("*") if p.is_file() and p.suffix.lower() in suffixes)
    return sorted(p for p in found if not any(p.startswith(d.rstrip("/") + "/") for d in skip))


# PURPOSE: BUILDS THE GRAPH OF EVERY PROGRAM, JCL MEMBER AND CSD EXTRACT IN A TREE; RETURNS IT WITH PARSE FAILURES
def system_graph(tree: Path, copybook_dirs: list[str], config: Config | None) -> tuple[Graph, dict[str, str]]:
    adapter = CobolAdapter(copybook_dirs)
    modules, failed = [], {}
    for path in files_with(tree, PROGRAM_SUFFIXES, copybook_dirs):
        try:
            modules.append(adapter.parse(tree / path, tree))
        except CobolSyntaxError as exc:
            failed[path] = "; ".join(f"{where}: {msg}" for where, msg in exc.errors[:3])
    jobs = [job for path in files_with(tree, JCL_SUFFIXES, []) for job in parse_jcl(tree / path, tree)]
    csd = [d for path in files_with(tree, CSD_SUFFIXES, []) for d in parse_csd(tree / path, tree)]
    return graph_from(modules, jobs, config, csd), failed


# PURPOSE: LINE OF EACH COMPONENT'S RELIED_ON_BY LIST IN THE CONFIG TEXT, KEYED BY COMPONENT ID
def reliant_lines(text: str) -> dict[str, int]:
    root = yaml.compose(text)
    found = {}
    for key, value in root.value:
        if key.value == "components":
            for item in value.value:
                fields = {k.value: v for k, v in item.value}
                if "relied_on_by" in fields:
                    found[fields["id"].value] = fields["relied_on_by"].start_mark.line + 1
    return found


# PURPOSE: KEEPS THE FIRST DICT FOR EACH VALUE OF THE KEY FIELDS, IN ORDER
def unique(items: list[dict], *fields: str) -> list[dict]:
    found: dict[tuple, dict] = {}
    for item in items:
        found.setdefault(tuple(repr(item[f]) for f in fields or sorted(item)), item)
    return list(found.values())


# PURPOSE: GAPS THE READER MUST KNOW ABOUT: UNANALYZED FILES, PARSE FAILURES, BROKEN AND RUN-TIME-ONLY CALLS
def gaps(walk: ImpactWalk, graph: Graph, best: dict[str, Reached], what: What, failed: dict[str, str]) -> list[dict]:
    found = [{"description": f"{path} changed but was not analyzed: {reason}", "provenance": {"file": path, "line": 1}}
             for path, reason in what.not_analyzed.items()]
    found += [{"description": f"{path} could not be parsed: {problem}", "provenance": {"file": path, "line": 1}}
              for path, problem in (what.problems | failed).items()]
    for node in best:
        if walk.nodes[node].kind == "unresolved":
            found += [{"description": f"{e.src} {e.kind} {walk.nodes[node].name}: {e.attributes['reason']}",
                       "provenance": e.provenance.model_dump(mode="json")} for e in walk.into.get(node, [])]
    if any(walk.nodes[node].kind == "program" for node in best):
        found += [{"description": f"{e.src} calls a program named only at run time ({e.attributes['reason']}); "
                                  "it may reach a changed or impacted program",
                   "provenance": e.provenance.model_dump(mode="json")}
                  for e in graph.unresolved if e.kind == "calls" and e.dst.startswith("unresolved:dynamic:")]
    return unique(found)


# PURPOSE: WHO, WHEN AND WHY FOR THE COMMITS IN THE RANGE, COPIED FROM THE COMMIT OBJECTS
def people_and_reasons(root: Path, shas: list[str]) -> tuple[list[dict], dict, list[dict]]:
    commits = [read_commit(root, sha) for sha in shas]
    who, why = [], []
    for commit in commits:
        found = trailers(commit.message)
        roles = who_of(commit, found)
        who.append({"role": "author", "id": roles.implementer.email or roles.implementer.name,
                    "source": f"git author, {roles.implementer.provenance}"})
        who.append({"role": "committer", "id": roles.committer.email or roles.committer.name,
                    "source": f"git committer, {roles.committer.provenance}"})
        who += [{"role": "approver", "id": a.email or a.name, "source": f"Approved-by trailer, {a.provenance}"}
                for a in roles.approvers]
        why += [{"kind": "ticket", "ref": t.id, "found_in": f"commit {t.found_in}, {t.provenance}"}
                for t in why_of(commit, found).tickets]
    when = {"authored_at": commits[0].author.at, "committed_at": commits[-1].committer.at}
    return unique(who, "role", "id"), when, unique(why, "ref")


# PURPOSE: THE IMPACT PREDICATE FOR A COMMIT OR RANGE, VALIDATED AGAINST ITS SCHEMA
def impact(root: Path, revisions: str, copybook_dirs: list[str] = (), config_path: str = CONFIG_NAME) -> dict:
    root = Path(root)
    copybook_dirs = list(copybook_dirs)
    shas = commits_in(root, revisions)
    first = read_commit(root, shas[0])
    base, head = (first.parents[0] if first.parents else None), shas[-1]
    with tempfile.TemporaryDirectory() as scratch:
        after = checkout_tree(root, head, Path(scratch) / "after")
        before = checkout_tree(root, base, Path(scratch) / "before") if base else None
        what = what_in(before, after, tree_diffs(root, base, head), copybook_dirs)
        config_file = after / config_path
        config = load_config(config_file) if config_file.is_file() else None
        reliant_at = reliant_lines(config_file.read_text(encoding="utf-8")) if config else {}
        graph, failed = system_graph(after, copybook_dirs, config)
    walk = ImpactWalk(graph)
    best, changed = walk.walk(what.entities)
    impacted = sorted(((node, r) for node, r in best.items()
                       if node not in changed and walk.nodes[node].kind not in NOT_REPORTED),
                      key=lambda item: (item[1].tier, item[0]))
    reliant = [{"id": system, "via_component": component["id"],
                "provenance": {"file": PurePosixPath(config_path).as_posix(), "line": reliant_at[component["id"]]}}
               for node in sorted(best) if (component := walk.nodes[node].attributes.get("component"))
               for system in component["relied_on_by"]]
    crypto = any(c.entity.kind == "crypto-call" for c in what.entities) or any(
        e.kind == "uses-crypto" for node in changed for e in walk.out.get(node, []))
    who, when, why = people_and_reasons(root, shas)
    predicate = {
        "change": {"vcs": "git", "repository": origin_url(root) or root.resolve().name,
                   "base": base or empty_tree(root), "head": head},
        "who": who,
        "when": when,
        "why": why,
        "changed": [{"id": c.entity.id, "kind": c.entity.kind, "name": c.entity.name,
                     "provenance": c.entity.provenance.model_dump(mode="json"), "change": c.change.value}
                    for c in what.entities],
        "impacted": [{"id": node, "kind": walk.nodes[node].kind, "name": walk.nodes[node].name,
                      "provenance": walk.nodes[node].provenance.model_dump(mode="json"),
                      "confidence": r.tier.name.lower(),
                      "via": [{"from": s.src, "to": s.dst, "edge": s.edge, "provenance": s.provenance.model_dump(mode="json")}
                              for s in r.via]}
                     for node, r in impacted],
        "reliant_systems": unique(reliant),
        "touches_crypto": crypto,
        "unresolved": gaps(walk, graph, best, what, failed),
        "engine": {"name": "changeproof", "version": __version__,
                   "adapters": [{"language": "cobol", "version": __version__, "parser": "antlr4-cobol85"},
                                {"language": "jcl", "version": __version__}]},
    }
    validate_predicate(PREDICATE_TYPES["impact"], predicate)
    return predicate
