from pathlib import Path
from typing import Any

from changeproof.adapters.base import EntityChange, IRModule, Observation, diff_by_id
from changeproof.adapters.java.ir import JavaSyntaxError, parse_java

__all__ = ["JavaAdapter", "JavaSyntaxError"]


class JavaAdapter:
    language = "java"

    # PURPOSE: PARSES ONE JAVA FILE INTO IR
    def parse(self, path: Path, root: Path) -> IRModule:
        return parse_java(path, root)

    # PURPOSE: COMPARES TWO VERSIONS OF A FILE BY ENTITY ID
    def diff(self, before: IRModule | None, after: IRModule | None) -> list[EntityChange]:
        return diff_by_id(before, after)

    # PURPOSE: RUNNING JAVA FOR CHARACTERIZATION TESTS IS NOT BUILT YET
    def run(self, module: IRModule, inputs: dict[str, Any]) -> list[Observation]:
        raise NotImplementedError("running Java for characterization tests is planned")
