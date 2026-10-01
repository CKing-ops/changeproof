from pathlib import Path
from typing import Any

from changeproof.adapters.base import EntityChange, IRModule, Observation, diff_by_id
from changeproof.adapters.cobol.driver import Field, driver_source, linkage_fields
from changeproof.adapters.cobol.gnucobol import LocalRunner, Run, Runner
from changeproof.adapters.cobol.ir import build_entities
from changeproof.adapters.cobol.parse import parse
from changeproof.adapters.cobol.preprocess import CopybookLibrary, preprocess


class CobolAdapter:
    language = "cobol"

    # PURPOSE: SETS THE COPYBOOK FOLDERS, RELATIVE TO THE ROOT PASSED TO PARSE; ROOT AND RUNNER ARE FOR RUN
    def __init__(self, copybook_dirs: list[str], root: Path = Path("."), runner: Runner | None = None) -> None:
        self.copybook_dirs = list(copybook_dirs)
        self.root = Path(root)
        self.runner = runner

    # PURPOSE: PREPROCESSES AND PARSES ONE PROGRAM INTO AN IR MODULE
    def parse(self, path: Path, root: Path) -> IRModule:
        source = preprocess(Path(path), Path(root), CopybookLibrary(Path(root), self.copybook_dirs))
        tree, tokens = parse(source)
        return IRModule(path=Path(path).relative_to(root).as_posix(), language=self.language,
                        entities=build_entities(source, tree, tokens))

    # PURPOSE: COMPARES TWO VERSIONS OF A PROGRAM BY ENTITY ID
    def diff(self, before: IRModule | None, after: IRModule | None) -> list[EntityChange]:
        return diff_by_id(before, after)

    # PURPOSE: RUNS A LINKAGE SUBPROGRAM UNDER GNUCOBOL ON EACH INPUT SET, TRACING WHICH LINES RAN
    def execute(self, module: IRModule, inputs: list[dict[str, Any]]) -> tuple[list[Field], list[Run]]:
        program = next(e for e in module.entities if e.kind == "program")
        fields = linkage_fields(module)
        elementary = [f for f in fields if f.picture]
        runner = self.runner or LocalRunner()
        runs = runner.run(self.root / module.path, program.name, driver_source(program, fields),
                          [self.root / d for d in self.copybook_dirs],
                          [[str(values.get(f.name, f.default)) for f in elementary] for values in inputs])
        return elementary, runs

    # PURPOSE: ONE OBSERVATION OF THE PROGRAM'S LINKAGE ITEMS AFTER A CALL WITH THESE INPUTS
    def run(self, module: IRModule, inputs: dict[str, Any]) -> list[Observation]:
        program = next(e for e in module.entities if e.kind == "program")
        elementary, (found,) = self.execute(module, [inputs])
        return [Observation(entity_id=program.id, inputs={f.name: str(inputs.get(f.name, f.default))
                                                          for f in elementary},
                            outputs=found.output | {"rc": found.rc}, provenance=program.provenance)]
