import re
from dataclasses import dataclass, field
from decimal import Decimal

from changeproof.adapters.base import Entity, IRModule
from changeproof.provenance import Provenance

PICTURE_REPEAT_RE = re.compile(r"(.)\((\d+)\)")
UNSUPPORTED_RE = re.compile(r"\b(COMP(?:UTATIONAL)?(?:-\d)?|BINARY|PACKED-DECIMAL|POINTER|INDEX|OCCURS|REDEFINES)\b",
                            re.IGNORECASE)
QUOTED_RE = re.compile(r"'([^']*)'|\"([^\"]*)\"")
NUMBER_RE = re.compile(r"(?<![\w-])\d+(?:\.\d+)?(?![\w-])")
BUFFER = 64  # RENAME: MINIMUM WIDTH OF THE DRIVER'S ACCEPT BUFFER


@dataclass
class Field:
    name: str
    level: str
    picture: str | None
    provenance: Provenance
    values: dict[str, str] = field(default_factory=dict)  # 88-level name to its first literal
    read: bool = False

    # PURPOSE: VALUE A FIELD GETS WHEN A RUN DOES NOT SET IT
    @property
    def default(self) -> str:
        return "0" if self.shape["numeric"] else ""

    # PURPOSE: SIZE, SCALE AND SIGN OF THIS FIELD'S PICTURE
    @property
    def shape(self) -> dict:
        return parse_picture(self.picture)


# PURPOSE: SIZE, SCALE AND SIGN OF A DISPLAY PICTURE
def parse_picture(picture: str) -> dict:
    chars = PICTURE_REPEAT_RE.sub(lambda m: m[1] * int(m[2]), picture.upper())
    numeric = set(chars) <= set("S9VP")
    whole, _, fraction = chars.partition("V")
    return {"numeric": numeric, "signed": chars.startswith("S"), "digits": chars.count("9") if numeric else 0,
            "scale": fraction.count("9") if numeric else 0, "length": len(chars.replace("S", "").replace("V", ""))}


# PURPOSE: LITERALS OF A TEXT: QUOTED STRINGS AND UNSIGNED NUMBERS
def literals(text: str) -> tuple[list[str], list[str]]:
    quoted = [next(g for g in m.groups() if g is not None) for m in QUOTED_RE.finditer(text)]
    return quoted, NUMBER_RE.findall(QUOTED_RE.sub(" ", text))


# PURPOSE: LINKAGE ITEMS OF A PROGRAM IN DECLARATION ORDER, WITH 88 VALUES AND WHETHER THE PROGRAM READS THEM
def linkage_fields(module: IRModule) -> list[Field]:
    found: dict[str, Field] = {}  # RENAME: DATA ENTITY ID TO LINKAGE FIELD
    for e in module.entities:
        if e.kind == "data" and e.attributes.get("section") == "linkage":
            if bad := UNSUPPORTED_RE.search(e.attributes["text"]):
                raise ValueError(f"{e.name} at {e.provenance}: {bad[1].upper()} items are not supported "
                                 "by the characterization driver")
            found[e.id] = Field(e.name, e.attributes["level"], e.attributes.get("picture"), e.provenance)
        elif e.kind == "condition" and e.attributes.get("parent") in found:
            quoted, numbers = literals(e.attributes["text"].split("VALUE", 1)[-1])
            found[e.attributes["parent"]].values[e.name] = (quoted + numbers)[0]
    names = set()
    for e in module.entities:
        names.update(e.attributes.get("refs", []) if e.kind == "branch" else e.attributes.get("sources", []))
    for f in found.values():
        f.read = f.name in names or bool(names & set(f.values))
    return list(found.values())


# PURPOSE: CONDITION AND STATEMENT TEXTS THAT MENTION A FIELD OR ONE OF ITS 88 NAMES
def texts_about(f: Field, module: IRModule) -> list[str]:
    names = {f.name, *f.values}
    return [e.attributes["condition"] for e in module.entities
            if e.kind == "branch" and names & set(e.attributes["refs"])]


# PURPOSE: BOUNDARY VALUES FOR ONE FIELD: EACH LITERAL IT MEETS, ONE UNIT EITHER SIDE, ZERO AND THE MAXIMUM
def candidates(f: Field, module: IRModule) -> list[str]:
    shape = f.shape
    if not shape["numeric"]:
        if not f.read:
            return [f.default]
        pool = ["", *f.values.values(), *(q for t in texts_about(f, module) for q in literals(t)[0])]
        return list(dict.fromkeys(v for v in pool if len(v) <= shape["length"]))
    if not f.read:
        return [f.default]
    unit = Decimal(1).scaleb(-shape["scale"])
    top = Decimal(10) ** (shape["digits"] - shape["scale"]) - unit
    seen = {Decimal(0), top}
    for e in module.entities:
        for key in ("condition", "text"):
            if e.kind in ("branch", "flow") and key in e.attributes:
                for n in literals(e.attributes[key])[1]:
                    value = Decimal(n)
                    seen.update((value - unit, value, value + unit))
    if shape["signed"]:
        seen.add(-unit)
    low = -top if shape["signed"] else Decimal(0)
    return [format(v, "f") for v in sorted(v.quantize(unit) for v in seen
                                           if low <= v <= top and v == v.quantize(unit))]


# PURPOSE: FREE-FORMAT DRIVER THAT READS EVERY LINKAGE ITEM FROM STDIN, CALLS THE PROGRAM AND DISPLAYS THEM ALL
def driver_source(program: Entity, fields: list[Field]) -> str:
    elementary = [f for f in fields if f.picture]
    width = max([BUFFER, *(f.shape["length"] for f in elementary)])
    using = program.attributes.get("using") or [f.name for f in fields if f.level in ("01", "77")]
    lines = ["IDENTIFICATION DIVISION.", "PROGRAM-ID. CPDRIVER.", "DATA DIVISION.", "WORKING-STORAGE SECTION.",
             f"01 CP-BUF PIC X({width})."]
    lines += [f"{f.level} {f.name}" + (f" PIC {f.picture}." if f.picture else ".") for f in fields]
    lines.append("PROCEDURE DIVISION.")
    for f in elementary:
        source = "FUNCTION NUMVAL(CP-BUF)" if f.shape["numeric"] else "CP-BUF"
        lines += ["    ACCEPT CP-BUF", f"    MOVE {source} TO {f.name}"]
    lines.append(f"    CALL '{program.name}' USING " + " ".join(using))
    lines += [f"    DISPLAY '{f.name}=' {f.name}" for f in elementary]
    lines.append("    STOP RUN.")
    return "\n".join(lines) + "\n"
