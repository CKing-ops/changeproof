from pathlib import Path

import pytest
from pydantic import ValidationError

from changeproof.adapters import Adapter, AdapterRegistry, ChangeKind, Entity, IRModule, Observation, diff_by_id
from changeproof.provenance import Provenance


def entity(name: str, line: int, **attributes) -> Entity:
    return Entity(
        id=f"paragraph:{name}",
        kind="paragraph",
        name=name,
        provenance=Provenance(file="src/PAY.cbl", line=line),
        attributes=attributes,
    )


def module(*entities: Entity) -> IRModule:
    return IRModule(path="src/PAY.cbl", language="cobol", entities=list(entities))


class FakeAdapter:
    language = "fake"

    def parse(self, path: Path, root: Path) -> IRModule:
        return module(entity("MAIN", 1))

    def diff(self, before: IRModule | None, after: IRModule | None):
        return diff_by_id(before, after)

    def run(self, module: IRModule, inputs: dict) -> list[Observation]:
        return []


def test_provenance_renders_as_file_colon_line():
    assert str(Provenance(file="src/PAY.cbl", line=42)) == "src/PAY.cbl:42"
    assert str(Provenance(file="src/PAY.cbl", line=42, end_line=48)) == "src/PAY.cbl:42-48"


@pytest.mark.parametrize(
    "fields",
    [
        {"file": "src/PAY.cbl", "line": 0},
        {"file": "", "line": 1},
        {"file": "/abs/PAY.cbl", "line": 1},
        {"file": "../PAY.cbl", "line": 1},
        {"file": "src/PAY.cbl", "line": 9, "end_line": 3},
    ],
)
def test_provenance_rejects_invalid_locations(fields):
    with pytest.raises(ValidationError):
        Provenance(**fields)


def test_entity_cannot_exist_without_provenance():
    with pytest.raises(ValidationError, match="provenance"):
        Entity(id="paragraph:MAIN", kind="paragraph", name="MAIN")


def test_registry_returns_adapter_by_language():
    registry = AdapterRegistry()
    registry.register(FakeAdapter())
    assert isinstance(registry.get("fake"), Adapter)
    with pytest.raises(KeyError, match="no adapter for language 'ada'"):
        registry.get("ada")


def test_registry_rejects_objects_missing_the_interface():
    class Incomplete:
        language = "broken"

        def parse(self, path, root): ...

    with pytest.raises(TypeError, match="diff"):
        AdapterRegistry().register(Incomplete())


def test_registry_rejects_duplicate_language():
    registry = AdapterRegistry()
    registry.register(FakeAdapter())
    with pytest.raises(ValueError, match="already registered"):
        registry.register(FakeAdapter())


def test_diff_reports_added_removed_and_modified_entities():
    before = module(entity("MAIN", 10), entity("OLD", 20), entity("CALC", 30, statements=4))
    after = module(entity("MAIN", 12), entity("CALC", 32, statements=5), entity("NEW", 40))
    changes = {c.entity.name: c for c in diff_by_id(before, after)}

    assert set(changes) == {"OLD", "CALC", "NEW"}
    assert changes["OLD"].change is ChangeKind.REMOVED
    assert changes["OLD"].entity.provenance.line == 20
    assert changes["NEW"].change is ChangeKind.ADDED
    assert changes["CALC"].change is ChangeKind.MODIFIED
    assert changes["CALC"].previous.provenance.line == 30
    assert changes["CALC"].entity.provenance.line == 32


def test_diff_ignores_pure_line_moves():
    assert diff_by_id(module(entity("MAIN", 10)), module(entity("MAIN", 99))) == []


def test_diff_handles_new_and_deleted_files():
    added = diff_by_id(None, module(entity("MAIN", 1)))
    removed = diff_by_id(module(entity("MAIN", 1)), None)
    assert [c.change for c in added] == [ChangeKind.ADDED]
    assert [c.change for c in removed] == [ChangeKind.REMOVED]
