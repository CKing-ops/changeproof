"""Batch programs run on files built for each test, then their output files are read back.

A loader writes each file the program reads, with zero or one record laid out as the program reads it
(its READ ... INTO area, else the FD record). After the run an unloader reads every file the program
writes, laid out as the program writes it (its WRITE ... FROM area, else the FD record), and shows each
field of each record. Both are generated from the program's own SELECT and FD entries.
"""

import re
from dataclasses import dataclass

from changeproof.adapters.base import Entity, IRModule
from changeproof.adapters.cobol.driver import Field, buffer_width, fields_of, fill_lines, read_names
from changeproof.adapters.cobol.layout import Item, declaration, find, leaves, repeated, roots

INPUT_MODES = frozenset({"INPUT", "I-O"})
OUTPUT_MODES = frozenset({"OUTPUT", "EXTEND", "I-O"})
DROPPED_RE = re.compile(r"\b(?:FILE\s+)?STATUS\s+(?:IS\s+)?[\w-]+|\bACCESS\s+(?:MODE\s+)?(?:IS\s+)?\w+"
                        r"|\bRESERVE\s+\d+\s+(?:AREAS?)?|\bLOCK\s+MODE\s+(?:IS\s+)?\w+", re.IGNORECASE)
ORGANIZATION_RE = re.compile(r"\b(?:ORGANIZATION\s+(?:IS\s+)?)?(LINE\s+SEQUENTIAL|SEQUENTIAL|INDEXED|RELATIVE)\b",
                             re.IGNORECASE)
RECORD_CHOICES = ["1", "0"]  # RENAME: RECORD COUNTS TRIED FOR EACH FILE A PROGRAM READS
EXEC_KINDS = {"exec-cics": "EXEC CICS", "exec-sql": "EXEC SQL", "exec-dli": "EXEC DLI"}


@dataclass
class DataFile:
    entity: Entity
    records: list[Item]  # the FD's 01 records
    read_as: tuple[Item, Item] | None  # (root to declare, item whose leaves are filled) when the program reads it
    written_as: tuple[Item, Item] | None  # the same for what the program writes

    # PURPOSE: SELECT NAME
    @property
    def name(self) -> str:
        return self.entity.name

    # PURPOSE: ORGANIZATION, SEQUENTIAL WHEN NONE IS WRITTEN
    @property
    def organization(self) -> str:
        m = ORGANIZATION_RE.search(self.entity.attributes["text"])
        return " ".join(m[1].upper().split()) if m else "SEQUENTIAL"

    # PURPOSE: SELECT ENTRY FOR A GENERATED PROGRAM: KEYED FILES OPEN DYNAMIC, THE PROGRAM'S STATUS ITEM IS DROPPED
    def select(self, status: str) -> str:
        text = DROPPED_RE.sub("", self.entity.attributes["text"]).rstrip(" .")
        access = " ACCESS MODE IS DYNAMIC" if self.organization == "INDEXED" else ""
        return f"    {text}{access} FILE STATUS IS {status}."


# PURPOSE: THE FIRST ROOT AND ITEM A READ ... INTO OR A WRITE ... FROM OF THIS FILE USES, ELSE ITS FD RECORD
def layout_of(module: IRModule, tops: dict[str, Item], file: str, records: list[Item], verbs: set[str]) -> tuple[Item, Item]:
    names = {r.name for r in records}
    for e in module.entities:
        if e.kind != "flow" or e.attributes["verb"] not in verbs:
            continue
        if e.attributes["verb"] == "READ" and e.attributes.get("file") == file:
            area = e.attributes["targets"][0]
        elif e.attributes["verb"] != "READ" and e.attributes["targets"][0] in names and e.attributes["sources"]:
            area = e.attributes["sources"][0]
        else:
            continue
        if found := find(tops, area):
            return found
    return records[0], records[0]


# PURPOSE: FILES THE PROGRAM OPENS, WITH HOW IT READS AND WRITES EACH; REFUSES CICS, SQL AND RELATIVE FILES
def data_files(module: IRModule) -> list[DataFile]:
    if exec_block := next((e for e in module.entities if e.kind in EXEC_KINDS), None):
        raise ValueError(f"uses {EXEC_KINDS[exec_block.kind]} at {exec_block.provenance}; stand-ins for CICS, Db2 "
                         "and IMS calls are planned")
    tops = roots(module)
    found = []
    for e in module.entities:
        if e.kind != "file" or not (modes := set(e.attributes.get("opened", []))):
            continue
        records = [t for t in tops.values() if t.entity.attributes.get("fd") == e.name]
        f = DataFile(e, records, None, None)
        if f.organization == "RELATIVE":
            raise ValueError(f"{e.name} at {e.provenance}: RELATIVE files are not supported by the characterization driver")
        if not records:
            raise ValueError(f"{e.name} at {e.provenance}: no FD record found")
        if modes & INPUT_MODES:
            f.read_as = layout_of(module, tops, e.name, records, {"READ"})
        if modes & OUTPUT_MODES:
            f.written_as = layout_of(module, tops, e.name, records, {"WRITE", "REWRITE"})
        found.append(f)
    return found


# PURPOSE: WHAT EACH TEST SETS, PER FILE READ: ITS RECORD COUNT THEN EVERY FIELD OF THE RECORD
def file_fields(module: IRModule, files: list[DataFile]) -> dict[str, list[Field]]:
    read, qualify = read_names(module), repeated(module)
    found = {}
    for f in files:
        if f.read_as:
            top, item = f.read_as
            count = Field(f.name, "01", "9", f.entity.provenance, key=f"{f.name}:records", ref="CP-COUNT",
                          choices=RECORD_CHOICES)
            found[f.name] = [count, *fields_of(module, [(top, leaf) for leaf in leaves(top, item, read, qualify)])]
    return found


# PURPOSE: DECLARATIONS OF EVERY FD RECORD AND EVERY OTHER LAYOUT A GENERATED PROGRAM USES
def data_division(files: list[DataFile], layouts: list[Item], extra: list[str]) -> list[str]:
    lines = ["DATA DIVISION.", "FILE SECTION."]
    for f in files:
        lines.append(f"FD {f.name}.")
        lines += [line for r in f.records for line in declaration(r)]
    lines.append("WORKING-STORAGE SECTION.")
    lines += extra
    records = {r.entity.id for f in files for r in f.records}
    seen = set()
    for top in layouts:
        if top.entity.id not in records and top.entity.id not in seen:
            seen.add(top.entity.id)
            lines += declaration(top)
    return lines


# PURPOSE: HEADER AND FILE-CONTROL OF A GENERATED PROGRAM
def environment(program: str, files: list[DataFile]) -> list[str]:
    return ["IDENTIFICATION DIVISION.", f"PROGRAM-ID. {program}.", "ENVIRONMENT DIVISION.",
            "INPUT-OUTPUT SECTION.", "FILE-CONTROL.",
            *(f.select(f"CP-ST-{n}") for n, f in enumerate(files, 1))]


# PURPOSE: TRUE WHEN THE AREA IS ONE OF THE FILE'S OWN FD RECORDS
def is_record(f: DataFile, item: Item) -> bool:
    return any(item.entity.id == r.entity.id for r in f.records)


# PURPOSE: PROGRAM THAT WRITES EACH FILE THE PROGRAM READS FROM ONE TEST'S STDIN
def loader_source(files: list[DataFile], groups: dict[str, list[Field]]) -> str:
    reading = [f for f in files if f.read_as]
    every = [field for fields in groups.values() for field in fields]
    lines = environment("CPLOAD", reading)
    lines += data_division(reading, [f.read_as[0] for f in reading],
                           [f"01 CP-BUF PIC X({buffer_width(every)}).", "01 CP-COUNT PIC 9(4).",
                            *(f"01 CP-ST-{n} PIC XX." for n in range(1, len(reading) + 1))])
    lines.append("PROCEDURE DIVISION.")
    for f in reading:
        item = f.read_as[1]
        source = "" if is_record(f, item) else f" FROM {item.name}"
        lines += [f"    OPEN OUTPUT {f.name}", *fill_lines([x for x in groups[f.name] if x.fill]),
                  f"    IF CP-COUNT > 0 WRITE {f.records[0].name}{source} END-IF", f"    CLOSE {f.name}"]
    lines.append("    STOP RUN.")
    return "\n".join(lines) + "\n"


# PURPOSE: PROGRAM THAT SHOWS EVERY FIELD OF EVERY RECORD IN EACH FILE THE PROGRAM WRITES, AS FILE#N.FIELD=VALUE
def unloader_source(module: IRModule, files: list[DataFile]) -> str:
    writing = [f for f in files if f.written_as]
    read, qualify = read_names(module), repeated(module)
    lines = environment("CPUNLOAD", writing)
    lines += data_division(writing, [f.written_as[0] for f in writing],
                           ["01 CP-N PIC 9(5).", "01 CP-EOF PIC X.",
                            *(f"01 CP-ST-{n} PIC XX." for n in range(1, len(writing) + 1))])
    lines.append("PROCEDURE DIVISION.")
    for n, f in enumerate(writing, 1):
        top, item = f.written_as
        into = "" if is_record(f, item) else f" INTO {item.name}"
        shown = [f"            DISPLAY '{f.name}#' CP-N '.{leaf.key}=' {leaf.ref}"
                 for leaf in leaves(top, item, read, qualify)]
        lines += [f"    OPEN INPUT {f.name}",
                  f"    IF CP-ST-{n} = '00'",
                  "        MOVE 0 TO CP-N", "        MOVE 'N' TO CP-EOF",
                  "        PERFORM UNTIL CP-EOF = 'Y'",
                  f"            READ {f.name} NEXT RECORD{into}",
                  "                AT END MOVE 'Y' TO CP-EOF",
                  "            END-READ",
                  f"            IF CP-EOF = 'N' AND CP-ST-{n} = '00'",
                  "            ADD 1 TO CP-N",
                  *shown,
                  "            ELSE MOVE 'Y' TO CP-EOF",
                  "            END-IF",
                  "        END-PERFORM",
                  f"        CLOSE {f.name}",
                  "    END-IF"]
    lines.append("    STOP RUN.")
    return "\n".join(lines) + "\n"
