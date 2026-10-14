"""The Java behaviour check: probes built from the base, replayed at the head, compared output by output."""

import importlib.util
import shutil
from pathlib import Path

import pytest

from changeproof.characterize import java as probe
from changeproof.equivalence import equivalence
from changeproof.impact.run import impact
from changeproof.pack import inside_blocks

FIXTURE = Path(__file__).parent / "fixtures" / "java_behaviour"
_spec = importlib.util.spec_from_file_location("java_behaviour_seed", FIXTURE / "seed.py")
_seed = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_seed)

pytestmark = pytest.mark.skipif(shutil.which("javac") is None, reason="needs a JDK")


@pytest.fixture(scope="module")
def repo(tmp_path_factory):
    root = tmp_path_factory.mktemp("rules") / "repo"
    return root, _seed.seed(root)


def java_tests(run, cls=None):
    return [t for t in run.predicate["tests"] if t["target"]["provenance"]["file"].endswith(".java")
            and (cls is None or t["target"]["name"] == cls)]


def test_the_probe_picks_static_methods_and_no_argument_classes_and_says_why_it_skips_others():
    targets, untested = probe.targets(_seed.SYSTEM)
    assert {t.label for t in targets} >= {
        "Limits.clamp(int,int,int)", "Limits.overLimit(long)", "Masking.mask(String)", "Rates.bandFor(long)",
        "Rates.interest(long,int)", "Calendar.isLeap(int)", "Tally.add(long)", "Tally.count()", "Tally.sum()"}
    router = next(u for u in untested if u["program"] == "Router")
    assert "constructor" in router["reason"] and router["provenance"]["file"].endswith("Router.java")
    tally = next(t for t in targets if t.label == "Tally.add(long)")
    assert tally.observers == ["count", "sum"]


def test_inputs_come_from_type_boundaries_and_the_method_s_own_literals():
    targets, _ = probe.targets(_seed.SYSTEM)
    over = next(t for t in targets if t.label == "Limits.overLimit(long)")
    values = {case[0] for case in probe.cases(over)}
    assert {"49999", "50000", "50001", "0", "-1", str(-2**63), str(2**63 - 1)} <= values
    assert len(probe.cases(over)) <= probe.MAX_CASES


def test_a_refactor_is_equivalent_and_a_behaviour_change_is_caught(repo):
    root, shas = repo
    refactor = equivalence(root, shas["refactor"], scope="full-suite")
    assert java_tests(refactor, "Rates") and all(t["result"] == "same" for t in java_tests(refactor))
    changed = equivalence(root, shas["masking"], scope="full-suite")
    different = [t for t in java_tests(changed) if t["result"] != "same"]
    assert different and {t["target"]["name"] for t in different} == {"Masking"}
    outside = equivalence(root, shas["masking"])
    assert java_tests(outside) and not java_tests(outside, "Masking")
    assert all(t["result"] == "same" for t in java_tests(outside))
    assert "java" in outside.predicate["environment"]["runner"]


def test_values_that_change_on_every_run_are_left_out_not_called_different(repo):
    root, shas = repo
    found = equivalence(root, shas["refactor"], scope="full-suite")
    assert not java_tests(found, "Stamps")
    stamps = next(u for u in found.predicate["untested"] if u.get("program") == "Stamps")
    assert "two runs of the base" in stamps["reason"]


def test_exit_check_the_probe_catches_planted_java_bugs(tmp_path):
    base = tmp_path / "base"
    shutil.copytree(_seed.SYSTEM, base)
    baseline = probe.run_tree(base, probe.targets(base)[0], tmp_path / "base-out")
    caught = []
    for n, (name, old, new) in enumerate(_seed.MUTATIONS):
        mutant = tmp_path / f"m{n}"
        shutil.copytree(_seed.SYSTEM, mutant)
        path = mutant / _seed.RULES / name
        assert old in path.read_text()
        path.write_text(path.read_text().replace(old, new, 1))
        found = probe.run_tree(mutant, baseline.targets, tmp_path / f"m{n}-out")
        if any(found.outputs[k] != v for k, v in baseline.stable().items()):
            caught.append(n)
    assert len(caught) == len(_seed.MUTATIONS), caught


def test_without_a_jdk_java_classes_are_listed_untested(repo, monkeypatch):
    root, shas = repo
    monkeypatch.setattr(probe, "JDK", None)
    found = equivalence(root, shas["refactor"], scope="full-suite")
    assert not java_tests(found)
    assert any("no JDK" in u["reason"] for u in found.predicate["untested"])
    assert found.predicate["verdict"] == "inconclusive"


def test_the_pack_report_lists_the_java_classes_inside_the_impact_set(repo):
    root, shas = repo
    full = equivalence(root, shas["masking"], scope="full-suite").predicate
    lines = [text for _, text in inside_blocks(impact(root, shas["masking"]), full)]
    masking = next(line for line in lines if line.startswith("Inside the impact set: Masking"))
    assert "different: behaviour this change altered" in masking
    assert any(line.startswith("different: Masking test Masking.mask(String)#") for line in lines)
