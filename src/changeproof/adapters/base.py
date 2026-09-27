"""Language adapter contract: parse -> IR, diff -> entities, run -> observations.

Adapters plug in by language key. Nothing in here names a language, so adding one never
touches these models (CLAUDE.md rule 8).
"""

from enum import StrEnum
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

from changeproof.provenance import Provenance


class Entity(BaseModel):
    """One fact the adapter extracted from source, e.g. a program, paragraph, field or call."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str = Field(min_length=1)  # stable across edits: kind plus qualified name, never a line number
    kind: str = Field(min_length=1)
    name: str
    provenance: Provenance
    attributes: dict[str, Any] = {}


class IRModule(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    language: str
    entities: list[Entity] = []


class ChangeKind(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


class EntityChange(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    change: ChangeKind
    entity: Entity  # the after-version, or the before-version when removed
    previous: Entity | None = None


class Observation(BaseModel):
    """What running an entity produced for one set of inputs (characterization tests, Week 8)."""

    model_config = ConfigDict(extra="forbid")

    entity_id: str
    inputs: dict[str, Any]
    outputs: dict[str, Any]
    provenance: Provenance


@runtime_checkable
class Adapter(Protocol):
    language: str

    def parse(self, path: Path, root: Path) -> IRModule: ...

    def diff(self, before: IRModule | None, after: IRModule | None) -> list[EntityChange]: ...

    def run(self, module: IRModule, inputs: dict[str, Any]) -> list[Observation]: ...


# PURPOSE: COMPARES TWO VERSIONS OF A MODULE BY ENTITY ID, IGNORING LINES THAT ONLY MOVED
def diff_by_id(before: IRModule | None, after: IRModule | None) -> list[EntityChange]:
    old = {e.id: e for e in before.entities} if before else {}  # RENAME: BEFORE-VERSION ENTITIES BY ID
    new = {e.id: e for e in after.entities} if after else {}  # RENAME: AFTER-VERSION ENTITIES BY ID
    changes = [EntityChange(change=ChangeKind.REMOVED, entity=old[i]) for i in old.keys() - new.keys()]
    changes += [EntityChange(change=ChangeKind.ADDED, entity=new[i]) for i in new.keys() - old.keys()]
    changes += [
        EntityChange(change=ChangeKind.MODIFIED, entity=new[i], previous=old[i])
        for i in old.keys() & new.keys()
        if (old[i].kind, old[i].name, old[i].attributes) != (new[i].kind, new[i].name, new[i].attributes)
    ]
    return sorted(changes, key=lambda c: (c.entity.provenance.file, c.entity.provenance.line, c.entity.id))
