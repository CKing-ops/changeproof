"""Java behaviour check: probe cases built from the base, run at the base and the head, compared output by output.

Needs only a JDK (java and javac), no build tool and no network. The sources of a tree are compiled
together, so a project whose main code needs third-party jars is reported untested. A probe case calls
one public method: a static method, or an instance method on an object made with a public no-argument
constructor, after which every public no-argument getter of that object is read too, so a method that
returns nothing still shows what it changed. Inputs are each parameter type's boundaries plus the
literals written in the method, one parameter varied at a time. Every case runs twice at the base and
twice at the head; a method with a case whose two results differ (time, randomness, identity hashes)
is left out rather than reported.
"""

import base64
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from importlib.resources import files
from pathlib import Path

from changeproof.adapters.java import JavaAdapter, JavaSyntaxError
from changeproof.change.record import JAVA_SUFFIXES
from changeproof.impact.run import files_with
from changeproof.signer import digest

MAX_CASES = 48  # RENAME: PROBE CASES PER METHOD AT MOST
MAX_POOL = 16  # RENAME: VALUES TRIED PER PARAMETER AT MOST
TIMEOUT = 900  # RENAME: SECONDS ONE PROBE RUN OF A WHOLE TREE MAY TAKE
SKIPPED = frozenset({"<init>", "<clinit>", "<instance-init>", "main"})  # RENAME: METHODS NEVER PROBED
WIRE = {"String...": "String[]", "int...": "int[]", "long...": "long[]", "byte...": "byte[]"}  # RENAME: VARARGS TO ARRAYS
INTEGRAL = {"int": 32, "long": 64, "short": 16, "byte": 8, "Integer": 32, "Long": 64}  # RENAME: TYPE TO BIT WIDTH
DECIMAL = frozenset({"double", "float", "Double"})
STRINGS = frozenset({"String", "CharSequence"})
ARRAYS = frozenset({"byte[]", "int[]", "long[]", "String[]"})
BOXED = frozenset({"Integer", "Long", "Boolean", "Double"})
SUPPORTED = frozenset(INTEGRAL) | DECIMAL | STRINGS | ARRAYS | BOXED | {"char", "boolean"}
NUMBER = re.compile(r"(?<![\w.])(-?\d+)[lL]?(?![\w.])")
TEXT = re.compile(r'"((?:[^"\\\n]|\\.)*)"')
CHAR = re.compile(r"'([^'\\])'")


# PURPOSE: PATHS OF JAVA AND JAVAC WHEN BOTH ARE ON THE PATH
def find_jdk() -> tuple[str, str] | None:
    java, javac = shutil.which("java"), shutil.which("javac")
    return (java, javac) if java and javac else None


JDK = find_jdk()  # RENAME: (JAVA, JAVAC) USED FOR PROBES, OR NONE WHEN NO JDK IS INSTALLED


@dataclass
class Target:
    label: str  # Class.method(params), as test ids and reports name it
    binary: str  # class name as the JVM loads it, nested classes joined with $
    method: str
    params: list[str]
    static: bool
    observers: list[str]
    literals: list[str]
    owner: dict  # the class as an entityRef
    file: str


@dataclass
class ProbeRun:
    targets: list[Target]
    outputs: dict[str, str] = field(default_factory=dict)  # case key to the probe's reply, first run
    repeat: dict[str, str] = field(default_factory=dict)  # the same, second run
    error: str | None = None

    # PURPOSE: METHODS WITH A CASE WHOSE TWO RUNS DISAGREE
    def shaky(self) -> set[str]:
        return {k.rpartition("#")[0] for k, v in self.outputs.items() if self.repeat.get(k) != v}

    # PURPOSE: CASES OF METHODS WHOSE TWO RUNS AGREE ON EVERY CASE, WITH THEIR OUTPUT
    def stable(self) -> dict[str, str]:
        shaky = self.shaky()
        return {k: v for k, v in self.outputs.items() if k.rpartition("#")[0] not in shaky}


# PURPOSE: JAVA SOURCES OF A TREE THAT ARE NOT TEST CODE
def main_sources(tree: Path) -> list[str]:
    return [p for p in files_with(tree, JAVA_SUFFIXES, []) if "test" not in p.split("/")[:-1]]


# PURPOSE: AN ENTITY AS THE PREDICATE'S ENTITYREF
def entity_ref(entity) -> dict:
    return {"id": entity.id, "kind": entity.kind, "name": entity.name,
            "provenance": entity.provenance.model_dump(mode="json", exclude_none=True)}


# PURPOSE: NUMBERS, STRINGS AND CHARACTERS WRITTEN IN A METHOD, READ FROM ITS LINES
def literals_in(tree: Path, provenance) -> list[str]:
    lines = (tree / provenance.file).read_text(encoding="utf-8").splitlines()
    text = "\n".join(lines[provenance.line - 1:provenance.end_line or provenance.line])
    found = [f"n:{m}" for m in NUMBER.findall(text)] + [f"s:{m}" for m in TEXT.findall(text)]
    return list(dict.fromkeys(found + [f"c:{m}" for m in CHAR.findall(text)]))


# PURPOSE: WHY A PUBLIC METHOD CANNOT BE PROBED, OR NONE WHEN IT CAN
def unprobeable(method, constructible: bool) -> str | None:
    a = method.attributes
    params = [WIRE.get(p, p.removeprefix("java.lang.")) for p in a["params"]]
    if "abstract" in a["modifiers"]:
        return "abstract"
    if unknown := [p for p in params if p not in SUPPORTED]:
        return f"parameter types the probe cannot build ({unknown[0]})"
    if "static" in a["modifiers"]:
        return "returns nothing" if a["returns"] in (None, "void") else None
    return None if constructible else "no public constructor without arguments"


# PURPOSE: PROBE TARGETS IN A TREE, AND ONE UNTESTED ENTRY PER PUBLIC CLASS WITH METHODS THE PROBE CANNOT CALL
def targets(tree: Path, include=lambda path: True) -> tuple[list[Target], list[dict]]:
    tree, adapter = Path(tree), JavaAdapter()
    found, untested = [], []
    for path in (p for p in main_sources(tree) if include(p)):
        try:
            entities = adapter.parse(tree / path, tree).entities
        except JavaSyntaxError as exc:
            untested.append({"provenance": {"file": path, "line": 1}, "reason": f"does not parse: {exc}"})
            continue
        classes = {e.id: e for e in entities if e.kind == "class"}
        methods = [e for e in entities if e.kind == "method"]
        for cls in classes.values():
            if not public_class(cls, classes):
                continue
            own = [m for m in methods if m.attributes.get("scope") == cls.id and m.name not in SKIPPED
                   and "public" in m.attributes["modifiers"] and not m.attributes.get("implicit")]
            inits = [m for m in methods if m.attributes.get("scope") == cls.id and m.id.split("(")[0].endswith(".<init>")]
            constructible = cls.attributes["type_kind"] == "class" and "abstract" not in cls.attributes["modifiers"] \
                and (not inits or any(not m.attributes["params"] and "public" in m.attributes["modifiers"] for m in inits))
            observers = sorted({m.name for m in own if not m.attributes["params"] and "static" not in m.attributes["modifiers"]
                                and m.attributes["returns"] not in (None, "void")})
            reasons = {}
            for m in own:
                if reason := unprobeable(m, constructible):
                    reasons.setdefault(reason, 0)
                    reasons[reason] += 1
                    continue
                params = [WIRE.get(p, p.removeprefix("java.lang.")) for p in m.attributes["params"]]
                static = "static" in m.attributes["modifiers"]
                found.append(Target(f"{cls.name}.{m.name}({','.join(params)})", binary_name(cls, classes), m.name,
                                    params, static, [] if static else [o for o in observers if o != m.name],
                                    literals_in(tree, m.provenance), entity_ref(cls), path))
            if reasons:
                why = "; ".join(f"{n} {r}" for r, n in sorted(reasons.items(), key=lambda kv: -kv[1]))
                untested.append({"program": cls.name, "provenance": entity_ref(cls)["provenance"],
                                 "reason": f"{sum(reasons.values())} of {len(own)} public methods not probed: {why}"})
    return found, untested


# PURPOSE: TRUE FOR A PUBLIC CLASS OR ENUM THE PROBE CAN LOAD: TOP LEVEL, OR STATIC AND NESTED IN PUBLIC CLASSES
def public_class(cls, classes: dict) -> bool:
    a = cls.attributes
    if a["type_kind"] not in ("class", "enum") or "public" not in a["modifiers"]:
        return False
    outer = a.get("scope")
    return outer is None or ("static" in a["modifiers"] and outer in classes and public_class(classes[outer], classes))


# PURPOSE: THE JVM NAME OF A CLASS, NESTED CLASSES JOINED WITH $
def binary_name(cls, classes: dict) -> str:
    outer = cls.attributes.get("scope")
    return f"{binary_name(classes[outer], classes)}${cls.name}" if outer else cls.id.removeprefix("class:")


# PURPOSE: VALUES TO TRY FOR ONE PARAMETER TYPE: ITS BOUNDARIES, THEN THE METHOD'S OWN LITERALS AND THEIR NEIGHBOURS
def pool(kind: str, literals: list[str]) -> list[str | None]:
    numbers = [int(v[2:]) for v in literals if v.startswith("n:")]
    texts = [v[2:] for v in literals if v.startswith("s:")]
    if kind in INTEGRAL:
        low, high = -2 ** (INTEGRAL[kind] - 1), 2 ** (INTEGRAL[kind] - 1) - 1
        values = [0, 1, -1, low, high] + [n + d for n in numbers for d in (-1, 0, 1)]
        found = [str(v) for v in values if low <= v <= high]
    elif kind in DECIMAL:
        found = ["0.0", "1.0", "-1.0", "0.5", "NaN", "Infinity"] + [f"{n}.0" for n in numbers]
    elif kind in ("boolean", "Boolean"):
        found = ["false", "true"]
    elif kind == "char":
        found = ["a", "A", "0", " "] + [v[2:] for v in literals if v.startswith("c:")]
    elif kind in STRINGS:
        found = [None, "", "a", "abc", "1234", "A b", "12345678"] + texts
    elif kind == "String[]":
        found = [None, "", ",".join(encode(t) for t in ("a",)), ",".join(encode(t) for t in ("a", "", "abc"))]
    else:
        found = [None, "", "0", "1,-1,2"] + [str(n) for n in numbers[:4]]
    if kind in BOXED:
        found = [None] + found
    return list(dict.fromkeys(found))[:MAX_POOL]


# PURPOSE: THE PROBE CASES OF A TARGET: THREE SEEDS, THEN EACH PARAMETER MOVED THROUGH ITS POOL WHILE THE REST HOLD
def cases(target: Target) -> list[tuple[str | None, ...]]:
    pools = [pool(kind, target.literals) for kind in target.params]
    if not pools:
        return [()]
    seeds = [tuple(p[0] for p in pools), tuple(p[len(p) // 2] for p in pools), tuple(p[-1] for p in pools)]
    found = list(seeds) + [s[:i] + (v,) + s[i + 1:] for s in seeds for i, p in enumerate(pools) for v in p]
    return list(dict.fromkeys(found))[:MAX_CASES]


# PURPOSE: BASE64 OF UTF-8 TEXT
def encode(text: str) -> str:
    return base64.b64encode(text.encode()).decode()


# PURPOSE: ONE INPUT LINE FOR THE PROBE
def wire(target: Target, case: tuple) -> str:
    args = ["~" if v is None else "=" + encode(v) for v in case]
    return "\t".join([target.binary, target.method, "static" if target.static else "instance", ",".join(target.params),
                      ",".join(target.observers), *args])


# PURPOSE: ENVIRONMENT FOR JAVA AND JAVAC WITHOUT THE HOST'S JAVA_TOOL_OPTIONS, WHICH WOULD WRITE TO STDERR
def clean_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in ("JAVA_TOOL_OPTIONS", "JDK_JAVA_OPTIONS", "_JAVA_OPTIONS")}


# PURPOSE: JAVA VERSION AS THE PREDICATE RECORDS IT
def describe() -> str:
    found = subprocess.run([JDK[0], "-version"], capture_output=True, text=True, env=clean_env())
    return found.stderr.splitlines()[0].replace('"', "") if found.stderr else "java"


# PURPOSE: COMPILES THE TREE'S MAIN SOURCES AND THE PROBE; RETURNS THE FIRST COMPILER ERROR, OR NONE
def compile_tree(tree: Path, out: Path) -> str | None:
    out.mkdir(parents=True, exist_ok=True)
    listing = out.parent / f"{out.name}-sources.txt"
    probe = files("changeproof.characterize").joinpath("Probe.java")
    listing.write_text("\n".join([str(tree / p) for p in main_sources(tree)] + [str(probe)]), encoding="utf-8")
    found = subprocess.run([JDK[1], "-d", str(out), "-encoding", "UTF-8", "-nowarn", "-proc:none", "-Xlint:none",
                            "-XDsuppressNotes", f"@{listing}"], capture_output=True, text=True, env=clean_env())
    if found.returncode:
        first = next((line for line in found.stderr.splitlines() if "error" in line), found.stderr.strip()[:300])
        return first.replace(f"{tree}/", "")
    return None


# PURPOSE: RUNS EVERY CASE OF THE TARGETS ONCE IN ONE JVM; ONE REPLY PER CASE KEY, MISSING IF THE JVM DIED
def run_once(out: Path, keyed: list[tuple[str, str]]) -> dict[str, str]:
    found = subprocess.run([JDK[0], "-Xss4m", "-cp", out.name, "Probe"], input="\n".join(line for _, line in keyed) + "\n",
                           capture_output=True, text=True, timeout=TIMEOUT, env=clean_env(), cwd=out.parent)
    return dict(zip((k for k, _ in keyed), found.stdout.splitlines()))


# PURPOSE: CASE KEYS AND INPUT LINES FOR THE TARGETS
def keyed_cases(chosen: list[Target]) -> list[tuple[str, str]]:
    return [(f"{t.label}#{n:02d}", wire(t, c)) for t in chosen for n, c in enumerate(cases(t), 1)]


# PURPOSE: COMPILES A TREE AND RUNS THE TARGETS' CASES TWICE, SO UNSTABLE CASES CAN BE LEFT OUT
def run_tree(tree: Path, chosen: list[Target], scratch: Path) -> ProbeRun:
    out = Path(scratch) / "classes"
    if error := compile_tree(Path(tree), out):
        return ProbeRun(chosen, error=error)
    # Base and head run from the same folder and class path, so code that reads user.dir or
    # java.class.path sees the same values on both sides.
    link = Path(scratch).parent / "run" / "classes"
    link.parent.mkdir(parents=True, exist_ok=True)
    link.unlink(missing_ok=True)
    link.symlink_to(out.resolve(), target_is_directory=True)
    keyed = keyed_cases(chosen)
    return ProbeRun(chosen, run_once(link, keyed), run_once(link, keyed))


# PURPOSE: ONE UNTESTED ENTRY PER CLASS OF THE TARGETS, ALL WITH THE SAME REASON
def classes_untested(chosen: list[Target], reason: str) -> list[dict]:
    owners = {t.owner["id"]: t.owner for t in chosen}
    return [{"program": o["name"], "provenance": o["provenance"], "reason": reason} for o in owners.values()]


# PURPOSE: TEST AND UNTESTED ENTRIES FOR THE JAVA CLASSES IN SCOPE: BASE CASES REPLAYED AT THE HEAD
def compare(before: Path | None, after: Path, include, scratch: Path) -> tuple[list[dict], list[dict]]:
    if before is None:
        chosen, untested = targets(after, include)
        return [], untested + classes_untested(chosen, "not in the base, so there is nothing to compare with")
    chosen, untested = targets(before, include)
    if not chosen:
        return [], untested
    if JDK is None:
        return [], untested + classes_untested(chosen, "no JDK (java and javac) on the PATH, so Java was not run")
    base = run_tree(before, chosen, Path(scratch) / "base")
    if base.error:
        return [], untested + classes_untested(chosen, f"does not compile at the base with the JDK alone: {base.error}")
    head = run_tree(after, chosen, Path(scratch) / "head")
    stable, tests, shaky = base.stable(), [], {}
    moving = head.shaky()
    for t in chosen:
        for n in range(1, len(cases(t)) + 1):
            key = f"{t.label}#{n:02d}"
            if key not in stable or t.label in moving:
                shaky.setdefault(t.owner["id"], [t.owner, 0])[1] += 1
                continue
            got = head.outputs.get(key)
            result = "error" if got is None else "same" if got == stable[key] else "different"
            tests.append({"id": key, "target": t.owner, "result": result, "baseline_output": digest(stable[key].encode()),
                          "candidate_output": digest((got or head.error or "no reply").encode())})
    untested += [{"program": owner["name"], "provenance": owner["provenance"],
                  "reason": f"{count} probe cases gave different results on two runs of the base or of the head "
                            "(time, randomness or identity), so they are left out"} for owner, count in shaky.values()]
    return tests, untested
