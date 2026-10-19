"""Record layouts rebuilt from IR data entities, for the generated programs that fill and read them.

A generated program declares a layout as the program does, so packed and binary numbers, tables and
redefinitions keep their bytes. Each elementary occurrence becomes one leaf with the name a run's
input or output is keyed by.
"""

import re
from dataclasses import dataclass, field
from itertools import product

from changeproof.adapters.base import Entity, IRModule

USAGE_RE = re.compile(r"\b(?:USAGE\s+(?:IS\s+)?)?(COMP(?:UTATIONAL)?(?:-\d)?|BINARY|PACKED-DECIMAL|DISPLAY|POINTER"
                      r"|PROCEDURE-POINTER|FUNCTION-POINTER|INDEX)\b(?!-)", re.IGNORECASE)
OCCURS_RE = re.compile(r"\bOCCURS\s+(\d+)(\s+TO\b)?", re.IGNORECASE)
REDEFINES_RE = re.compile(r"\bREDEFINES\s+([\w-]+)", re.IGNORECASE)
REFUSED = frozenset({"POINTER", "PROCEDURE-POINTER", "FUNCTION-POINTER", "INDEX", "COMP-1", "COMP-2"})


@dataclass
class Item:
    entity: Entity
    children: list["Item"] = field(default_factory=list)

    # PURPOSE: DATA NAME, OR FILLER
    @property
    def name(self) -> str:
        return self.entity.name

    # PURPOSE: USAGE CLAUSE AS WRITTEN SHORT (COMP-3, COMP, BINARY), NONE FOR DISPLAY
    @property
    def usage(self) -> str | None:
        if not (m := USAGE_RE.search(self.entity.attributes["text"])):
            return None
        word = m[1].upper().replace("COMPUTATIONAL", "COMP")
        return None if word == "DISPLAY" else word

    # PURPOSE: TIMES THIS ITEM OCCURS, ONE WHEN IT IS NOT A TABLE
    @property
    def occurs(self) -> int:
        m = OCCURS_RE.search(self.entity.attributes["text"])
        if m and m[2]:
            raise ValueError(f"{self.name} at {self.entity.provenance}: OCCURS DEPENDING ON items are not supported "
                             "by the characterization driver")
        return int(m[1]) if m else 1

    # PURPOSE: NAME OF THE ITEM THIS ONE REDEFINES
    @property
    def redefines(self) -> str | None:
        m = REDEFINES_RE.search(self.entity.attributes["text"])
        return m[1].upper() if m else None


@dataclass
class Leaf:
    item: Item
    key: str  # how a run's inputs and outputs name this occurrence
    ref: str  # how a generated program refers to it
    usage: str | None
    fill: bool  # False under a redefinition the run does not fill, so the program's view of the bytes wins


# PURPOSE: ROOT ITEMS (01 AND 77) OF A MODULE'S DATA, EACH WITH ITS CHILDREN, IN SOURCE ORDER
def roots(module: IRModule) -> dict[str, Item]:
    items = {e.id: Item(e) for e in module.entities if e.kind == "data"}
    found = {}
    for item in items.values():
        if parent := item.entity.attributes.get("parent"):
            items[parent].children.append(item)
        else:
            found[item.entity.id] = item
    return found


# PURPOSE: THE ITEM WITH THIS NAME AND THE ROOT THAT HOLDS IT, PREFERRING A ROOT OF THAT NAME
def find(tops: dict[str, Item], name: str) -> tuple[Item, Item] | None:
    for top in sorted(tops.values(), key=lambda t: t.name != name):
        stack = [top]
        while stack:
            item = stack.pop()
            if item.name == name:
                return top, item
            stack.extend(item.children)
    return None


# PURPOSE: DECLARATION LINES FOR A ROOT ITEM AND EVERYTHING UNDER IT, PICTURES WRITTEN WITHOUT SPACES
def declaration(top: Item) -> list[str]:
    lines, stack = [], [top]
    while stack:
        item = stack.pop()
        text = item.entity.attributes["text"]
        if picture := item.entity.attributes.get("picture"):
            spaced = r"\s*".join(re.escape(c) for c in picture)
            text = re.sub(rf"\b(PIC(?:TURE)?)(\s+IS)?\s+{spaced}(?=\s)", rf"\1 {picture}", text, count=1,
                          flags=re.IGNORECASE)
        lines.append(text)
        stack.extend(reversed(item.children))
    return lines


# PURPOSE: READ LEAVES DECIDE WHICH VIEW OF A REDEFINED AREA A RUN FILLS: THE FIRST VIEW WITH ONE, ELSE THE BASE
def filled_views(items: list[Item], read: set[str]) -> set[str]:
    # PURPOSE: TRUE WHEN THE ITEM OR ANYTHING UNDER IT IS READ
    def reads(item: Item) -> bool:
        return item.name in read or any(reads(c) for c in item.children)
    skipped = set()
    for base in items:
        views = [base, *(i for i in items if i.redefines == base.name)]
        if base.redefines or len(views) == 1:
            continue
        chosen = next((v for v in views if reads(v)), base)
        skipped |= {v.entity.id for v in views if v is not chosen}
    return skipped


# PURPOSE: EVERY ELEMENTARY OCCURRENCE UNDER AN ITEM, WITH ITS KEY, REFERENCE AND WHETHER A RUN FILLS IT
def leaves(top: Item, item: Item, read: set[str], qualify: set[str]) -> list[Leaf]:
    found = []

    # PURPOSE: COLLECTS THE LEAVES UNDER ONE NODE, CARRYING TABLE SIZES, USAGE AND WHETHER IT IS FILLED
    def walk(node: Item, dims: list[int], usage: str | None, fill: bool) -> None:
        usage = node.usage or usage
        if usage in REFUSED:
            raise ValueError(f"{node.name} at {node.entity.provenance}: {usage} items are not supported "
                             "by the characterization driver")
        dims = dims + [node.occurs] * (node.occurs > 1)
        if node.children:
            skipped = filled_views(node.children, read)
            for child in node.children:
                walk(child, dims, usage, fill and child.entity.id not in skipped)
            return
        if node.name == "FILLER" or "picture" not in node.entity.attributes:
            return
        name = f"{node.name} OF {top.name}" if node.name in qualify and node is not top else node.name
        for subscript in product(*(range(1, n + 1) for n in dims)):
            found.append(Leaf(node, name + (f"({','.join(map(str, subscript))})" if subscript else ""),
                              name + (f" ({' '.join(map(str, subscript))})" if subscript else ""), usage, fill))

    walk(item, [], None, True)
    return found


# PURPOSE: DATA NAMES DECLARED MORE THAN ONCE, WHICH A GENERATED PROGRAM MUST QUALIFY
def repeated(module: IRModule) -> set[str]:
    seen: dict[str, int] = {}
    for e in module.entities:
        if e.kind == "data":
            seen[e.name] = seen.get(e.name, 0) + 1
    return {name for name, count in seen.items() if count > 1}
