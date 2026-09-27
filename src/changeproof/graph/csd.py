"""CICS resource definitions (CSD DEFINE statements): transactions, files and mapsets."""

import re
from dataclasses import dataclass
from pathlib import Path

from changeproof.provenance import Provenance

DEFINE_RE = re.compile(r"^\s*DEFINE\s+([A-Z]+)\(([^)]*)\)", re.IGNORECASE)
OPTION_RE = re.compile(r"\b([A-Z][A-Z0-9]*)\(([^)]*)\)", re.IGNORECASE)


@dataclass
class CsdDefinition:
    kind: str  # TRANSACTION, FILE, MAPSET, PROGRAM, ...
    name: str
    line: int
    file: str
    options: dict[str, tuple[str, int]]  # RENAME: OPTION NAME TO (VALUE, LINE IT IS ON)

    # PURPOSE: PROVENANCE FROM THE DEFINE LINE THROUGH THE LINE HOLDING AN OPTION
    def through(self, option: str) -> Provenance:
        last = self.options[option][1]
        return Provenance(file=self.file, line=self.line, end_line=last if last != self.line else None)


# PURPOSE: PARSES A CSD EXTRACT INTO ITS DEFINE STATEMENTS AND THEIR OPTIONS
def parse_csd(path: Path, root: Path) -> list[CsdDefinition]:
    rel = Path(path).relative_to(root).as_posix()  # RENAME: REPO-RELATIVE PATH USED IN PROVENANCE
    found: list[CsdDefinition] = []
    for number, raw in enumerate(Path(path).read_text(encoding="latin-1").splitlines(), 1):
        if raw.lstrip().startswith("*"):
            continue
        if m := DEFINE_RE.match(raw):
            found.append(CsdDefinition(m.group(1).upper(), m.group(2).strip().upper(), number, rel, {}))
            raw = raw[m.end():]
        if found:
            for option, value in OPTION_RE.findall(raw):
                found[-1].options.setdefault(option.upper(), (value.strip().upper(), number))
    return found
