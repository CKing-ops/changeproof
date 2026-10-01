"""Week 11 exit check on Apache Commons Lang at a pinned commit, fetched by scripts/fetch_java_corpus.py.

Skipped where the corpus has not been fetched. CI fetches it before the offline test runs.
scripts/java_impact_check.py runs all 16 commits of the window; these are the ones that show each case.
"""

import importlib.util
from pathlib import Path

import pytest

from changeproof.graph.check import check_edges
from changeproof.impact.run import run_impact, system_graph

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("java_impact_check", ROOT / "scripts" / "java_impact_check.py")
check = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(check)

pytestmark = pytest.mark.skipif(not (check.CORPUS / ".git").is_dir(), reason="run scripts/fetch_java_corpus.py first")

SORT_MEMBERS = "f3b9aca"  # RENAME: COMMIT THAT ONLY REORDERS MEMBERS
DEPRECATE = "f3de6a4"  # RENAME: COMMIT THAT ONLY ADDS @Deprecated
SECURE_RANDOM = "17c3208"  # RENAME: COMMIT THAT SWITCHES TO new SecureRandom()


@pytest.fixture(scope="module")
def head_graph():
    return system_graph(check.CORPUS, [], None)


# PURPOSE: IMPACT FOR ONE COMMIT OF THE CORPUS AND ITS CHANGES THAT LIE OUTSIDE EVERY HUNK
def run(short: str):
    sha = check.git("rev-parse", short)
    result = run_impact(check.CORPUS, sha)
    return result, check.outside_hunks(result, result.predicate["change"]["base"], sha)


# PURPOSE: EVERY FILE PARSES AND EVERY EDGE OF THE WHOLE PROJECT CITES A LINE THAT HOLDS ITS ANCHOR
def test_the_whole_project_parses_and_every_edge_cites_its_line(head_graph):
    graph, failed = head_graph
    assert failed == {}
    assert len(graph.nodes) > 10_000
    assert check_edges(graph, check.CORPUS) == []


# PURPOSE: REORDERING MEMBERS IS NOT A CHANGE
def test_sorting_members_changes_nothing():
    result, _ = run(SORT_MEMBERS)
    assert result.predicate["changed"] == []


# PURPOSE: AN ADDED ANNOTATION IS A CHANGE, AND EVERY CHANGE LIES IN A CHANGED HUNK
def test_an_added_annotation_is_seen_and_lies_in_its_hunk():
    result, outside = run(DEPRECATE)
    assert result.predicate["changed"] and outside == [] and not result.what.problems


# PURPOSE: A METHOD REFERENCE TO A JCA CLASS MARKS THE CHANGE AS TOUCHING CRYPTO
def test_a_secure_random_method_reference_touches_crypto():
    result, outside = run(SECURE_RANDOM)
    assert result.predicate["touches_crypto"] and outside == []
    assert any(c["kind"] == "crypto-call" for c in result.predicate["changed"])
