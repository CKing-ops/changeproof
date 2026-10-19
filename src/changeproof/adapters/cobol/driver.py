import re
from dataclasses import dataclass, field
from decimal import Decimal

from changeproof.adapters.base import Entity, IRModule
from changeproof.adapters.cobol.layout import Item, Leaf, declaration, filled_views, leaves, repeated, roots
from changeproof.provenance import Provenance

PICTURE_REPEAT_RE = re.compile(r"(.)\((\d+)\)")
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
    key: str = ""  # RENAME: NAME A RUN'S INPUTS AND OUTPUTS USE, WITH ITS SUBSCRIPT IN A TABLE
    ref: str = ""  # RENAME: HOW A GENERATED PROGRAM REFERS TO IT
    usage: str | None = None
    fill: bool = True
    choices: list[str] | None = None  # RENAME: FIXED VALUES TRIED INSTEAD OF BOUNDARY VALUES

    # PURPOSE: KEY AND REFERENCE DEFAULT TO THE DATA NAME
    def __post_init__(self) -> None:
        self.key = self.key or self.name
        self.ref = self.ref or self.name

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


# PURPOSE: NAMES THE PROGRAM'S CONDITIONS AND DATA FLOWS READ
def read_names(module: IRModule) -> set[str]:
    names = set()
    for e in module.entities:
        names.update(e.attributes.get("refs", []) if e.kind == "branch" else e.attributes.get("sources", []))
    return names


# PURPOSE: ONE FIELD PER LEAF, WITH ITS 88 VALUES AND WHETHER THE PROGRAM READS IT
def fields_of(module: IRModule, found: list[tuple[Item, Leaf]]) -> list[Field]:
    names = read_names(module)
    values: dict[str, dict[str, str]] = {}  # RENAME: DATA ENTITY ID TO ITS 88 NAMES AND FIRST LITERALS
    for e in module.entities:
        if e.kind == "condition" and "parent" in e.attributes:
            quoted, numbers = literals(e.attributes["text"].split("VALUE", 1)[-1])
            values.setdefault(e.attributes["parent"], {})[e.name] = (quoted + numbers)[0]
    fields = []
    for top, leaf in found:
        e = leaf.item.entity
        f = Field(leaf.item.name, e.attributes["level"], e.attributes["picture"], e.provenance,
                  values.get(e.id, {}), key=leaf.key, ref=leaf.ref, usage=leaf.usage, fill=leaf.fill)
        f.read = f.name in names or bool(names & set(f.values))
        fields.append(f)
    return fields


# PURPOSE: LINKAGE ROOTS OF A PROGRAM IN DECLARATION ORDER
def linkage_roots(module: IRModule) -> list[Item]:
    return [t for t in roots(module).values() if t.entity.attributes.get("section") == "linkage"]


# PURPOSE: LINKAGE LEAVES IN DECLARATION ORDER, EACH TABLE OCCURRENCE ITS OWN FIELD, WITH 88 VALUES AND READS
def linkage_fields(module: IRModule) -> list[Field]:
    tops = linkage_roots(module)
    skipped = filled_views(tops, read_names(module))
    qualify = repeated(module)
    found = [(t, leaf) for t in tops for leaf in leaves(t, t, read_names(module), qualify)]
    for t, leaf in found:
        leaf.fill = leaf.fill and t.entity.id not in skipped
    return fields_of(module, found)


# PURPOSE: BRANCHES WHOSE CONDITION READS A FIELD OR ONE OF ITS 88 NAMES
def branches_about(f: Field, module: IRModule) -> list[Entity]:
    names = {f.name, *f.values}
    return [e for e in module.entities if e.kind == "branch" and names & set(e.attributes["refs"])]


# PURPOSE: BOUNDARY VALUES FOR ONE FIELD: EACH LITERAL IT MEETS, ONE UNIT EITHER SIDE, ZERO AND THE MAXIMUM
def candidates(f: Field, module: IRModule) -> list[str]:
    if f.choices is not None:
        return list(f.choices)
    shape = f.shape
    if not shape["numeric"]:
        if not f.read:
            return [f.default]
        pool = ["", *f.values.values(), *(q for b in branches_about(f, module) for q in literals(b.attributes["condition"])[0])]
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


# PURPOSE: ON-POINT VALUES OF A FIELD: EACH LITERAL A CONDITION COMPARES IT WITH, IN THE FIELD'S FORMAT, WITH THE BRANCHES
def boundary_values(f: Field, module: IRModule) -> dict[str, set[str]]:
    if f.choices is not None:
        return {}
    shape = f.shape
    unit = Decimal(1).scaleb(-shape["scale"])
    found: dict[str, set[str]] = {}  # RENAME: ON-POINT VALUE TO THE BRANCH IDS THAT COMPARE THE FIELD WITH IT
    for branch in branches_about(f, module):
        quoted, numbers = literals(branch.attributes["condition"])
        values = quoted if not shape["numeric"] else [
            format(Decimal(n).quantize(unit), "f") for n in numbers if Decimal(n) == Decimal(n).quantize(unit)]
        for value in values:
            found.setdefault(value, set()).add(branch.id)
    return found


# PURPOSE: ACCEPT AND MOVE LINES THAT FILL EACH FIELD FROM ONE STDIN LINE
def fill_lines(fields: list[Field]) -> list[str]:
    lines = []
    for f in fields:
        source = "FUNCTION NUMVAL(CP-BUF)" if f.shape["numeric"] else "CP-BUF"
        lines += ["    ACCEPT CP-BUF", f"    MOVE {source} TO {f.ref}"]
    return lines


# PURPOSE: WIDTH OF THE ACCEPT BUFFER FOR THESE FIELDS
def buffer_width(fields: list[Field]) -> int:
    return max([BUFFER, *(f.shape["length"] for f in fields)])


# PURPOSE: FREE-FORMAT DRIVER THAT READS EVERY FILLED LINKAGE LEAF FROM STDIN, CALLS THE PROGRAM AND DISPLAYS THEM ALL
def driver_source(program: Entity, tops: list[Item], fields: list[Field]) -> str:
    filled = [f for f in fields if f.fill]
    using = program.attributes.get("using") or [t.name for t in tops]
    lines = ["IDENTIFICATION DIVISION.", "PROGRAM-ID. CPDRIVER.", "DATA DIVISION.", "WORKING-STORAGE SECTION.",
             f"01 CP-BUF PIC X({buffer_width(filled)})."]
    lines += [line for t in tops for line in declaration(t)]
    lines.append("PROCEDURE DIVISION.")
    lines += fill_lines(filled)
    lines.append(f"    CALL '{program.name}' USING " + " ".join(using))
    lines += [f"    DISPLAY '{f.key}=' {f.ref}" for f in fields]
    lines.append("    STOP RUN.")
    return "\n".join(lines) + "\n"
