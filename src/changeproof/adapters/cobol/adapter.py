from pathlib import Path
from typing import Any

from changeproof.adapters.base import EntityChange, IRModule, Observation, diff_by_id
from changeproof.adapters.cobol.ir import build_entities
from changeproof.adapters.cobol.parse import parse
from changeproof.adapters.cobol.preprocess import CopybookLibrary, preprocess


class CobolAdapter:
    language = "cobol"

    # PURPOSE: SETS THE COPYBOOK FOLDERS, RELATIVE TO THE ROOT PASSED TO PARSE
    def __init__(self, copybook_dirs: list[str]) -> None:
        self.copybook_dirs = list(copybook_dirs)

    # PURPOSE: PREPROCESSES AND PARSES ONE PROGRAM INTO AN IR MODULE
    def parse(self, path: Path, root: Path) -> IRModule:
        source = preprocess(Path(path), Path(root), CopybookLibrary(Path(root), self.copybook_dirs))
        tree, tokens = parse(source)
        return IRModule(path=Path(path).relative_to(root).as_posix(), language=self.language,
                        entities=build_entities(source, tree, tokens))

    # PURPOSE: COMPARES TWO VERSIONS OF A PROGRAM BY ENTITY ID
    def diff(self, before: IRModule | None, after: IRModule | None) -> list[EntityChange]:
        return diff_by_id(before, after)

    # PURPOSE: PLACEHOLDER UNTIL CHARACTERIZATION RUNS EXIST
    def run(self, module: IRModule, inputs: dict[str, Any]) -> list[Observation]:
        raise NotImplementedError("characterization runs are planned for Week 8")
