from pathlib import Path
from typing import Any

from changeproof.adapters.base import EntityChange, IRModule, Observation, diff_by_id
from changeproof.adapters.cobol.driver import Field, driver_source, linkage_fields, linkage_roots
from changeproof.adapters.cobol.files import data_files, file_fields, loader_source, unloader_source
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

    # PURPOSE: TRUE FOR A PROGRAM RUN AS A JOB ON ITS FILES, FALSE FOR A SUBPROGRAM CALLED WITH LINKAGE ITEMS ONLY
    def is_batch(self, module: IRModule) -> bool:
        program = next(e for e in module.entities if e.kind == "program")
        return bool(data_files(module)) or "using" not in program.attributes

    # PURPOSE: WHAT A RUN SETS: LINKAGE LEAVES, THEN FOR A BATCH PROGRAM THE RECORDS OF THE FILES IT READS
    def inputs(self, module: IRModule) -> list[Field]:
        program = next(e for e in module.entities if e.kind == "program")
        found = [f for f in linkage_fields(module) if f.fill] if "using" in program.attributes else []
        if self.is_batch(module):
            found += [f for fields in file_fields(module, data_files(module)).values() for f in fields if f.fill]
        return found

    # PURPOSE: RUNS THE PROGRAM UNDER GNUCOBOL ON EACH INPUT SET, TRACING WHICH LINES RAN
    def execute(self, module: IRModule, inputs: list[dict[str, Any]]) -> tuple[list[Field], list[Run]]:
        program = next(e for e in module.entities if e.kind == "program")
        runner = self.runner or LocalRunner()
        filled = self.inputs(module)
        rows = [[str(row.get(f.key, f.default)) for f in filled] for row in inputs]
        copybooks = [self.root / d for d in self.copybook_dirs]
        linkage = linkage_fields(module) if "using" in program.attributes else []
        driver = driver_source(program, linkage_roots(module), linkage) if linkage else None
        if not self.is_batch(module):
            return linkage, runner.run(self.root / module.path, program.name, driver, copybooks, rows)
        files = data_files(module)
        split = sum(f.fill for f in linkage)  # RENAME: HOW MANY OF A ROW'S VALUES ARE THE DRIVER'S LINKAGE ITEMS
        runs = runner.run_batch(self.root / module.path, program.name,
                                loader_source(files, file_fields(module, files)), unloader_source(module, files),
                                sorted({f.entity.attributes["assign"] for f in files}), copybooks,
                                [r[split:] for r in rows], driver, [r[:split] for r in rows])
        return filled, runs

    # PURPOSE: ONE OBSERVATION OF THE PROGRAM'S LINKAGE ITEMS AFTER A CALL WITH THESE INPUTS
    def run(self, module: IRModule, inputs: dict[str, Any]) -> list[Observation]:
        program = next(e for e in module.entities if e.kind == "program")
        _, (found,) = self.execute(module, [inputs])
        return [Observation(entity_id=program.id, inputs={f.key: str(inputs.get(f.key, f.default))
                                                          for f in self.inputs(module)},
                            outputs=found.output | {"rc": found.rc}, provenance=program.provenance)]
