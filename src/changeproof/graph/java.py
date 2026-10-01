"""Java entities into the dependency graph (ROADMAP Week 11).

Classes, methods and fields become nodes. Edges: a class contains its members and nested classes; a
class extends or implements another project class; a method calls a method; a method or field
initializer uses a field; a method uses a JCA crypto service. A call is resolved by the receiver's
declared type through imports, the same package and enclosing classes, then up the project's own
superclasses. Several overloads with the same number of arguments all get an edge, marked
`target_from: arity`, which the impact walk reads as probable. A call whose receiver type is not known
but whose name matches a project method is kept as an unresolved edge, so the gap is reported.
"""

from collections import defaultdict
from dataclasses import dataclass, field

from changeproof.adapters.base import Entity, IRModule

INITIALIZER_WORDS = {"<clinit>": "static", "<instance-init>": "{"}  # RENAME: INITIALIZER BLOCK TO THE TOKEN ITS LINE HOLDS


@dataclass
class TypeInfo:
    entity: Entity
    module: IRModule
    methods: dict[str, list[Entity]] = field(default_factory=lambda: defaultdict(list))
    fields: dict[str, Entity] = field(default_factory=dict)


class JavaIndex:
    # PURPOSE: INDEXES EVERY TYPE, METHOD, FIELD AND IMPORT IN THE PROJECT'S JAVA MODULES
    def __init__(self, modules: list[IRModule]) -> None:
        self.types: dict[str, TypeInfo] = {}  # RENAME: CLASS FQN TO WHAT IT DECLARES
        self.imports: dict[str, dict[str, str]] = {}  # RENAME: MODULE PATH TO SIMPLE NAME TO IMPORTED FQN
        self.wildcards: dict[str, list[str]] = {}  # RENAME: MODULE PATH TO PACKAGES IMPORTED WITH .*
        self.method_names: set[str] = set()
        for module in modules:
            self.imports[module.path], self.wildcards[module.path] = {}, []
            for e in module.entities:
                if e.kind == "class":
                    self.types[e.id.split(":", 1)[1]] = TypeInfo(e, module)
                elif e.kind == "import" and not e.attributes["static"]:
                    if e.name.endswith(".*"):
                        self.wildcards[module.path].append(e.name[:-2])
                    else:
                        self.imports[module.path][e.name.rsplit(".", 1)[-1]] = e.name
        for module in modules:
            for e in module.entities:
                if e.kind in ("method", "field"):
                    owner = self.types[e.attributes["scope"].split(":", 1)[1]]
                    if e.kind == "field":
                        owner.fields[e.name] = e
                    else:
                        name = e.id.split(":", 1)[1].rsplit("(", 1)[0].rsplit(".", 1)[1]
                        owner.methods[name].append(e)
                        self.method_names.add(name)

    # PURPOSE: PACKAGE OF A CLASS FQN, FOUND BY WALKING OUT OF ANY ENCLOSING CLASSES
    def package_of(self, fqn: str) -> str:
        while (outer := self.types[fqn].entity.attributes.get("scope")) is not None:
            fqn = outer.split(":", 1)[1]
        return fqn.rsplit(".", 1)[0] if "." in fqn else ""

    # PURPOSE: THE PROJECT CLASS A TYPE NAME MEANS FROM INSIDE A CLASS, OR NONE FOR A TYPE OUTSIDE THE PROJECT
    def resolve_type(self, written: str | None, context: str) -> str | None:
        if not written:
            return None
        written = written.removesuffix("...").split("[", 1)[0]
        if written in self.types:
            return written
        head, _, rest = written.partition(".")
        scope = context
        while scope:  # nested classes of this class and of each enclosing class
            if (candidate := f"{scope}.{head}") in self.types:
                return f"{candidate}.{rest}" if rest and f"{candidate}.{rest}" in self.types else candidate
            outer = self.types[scope].entity.attributes.get("scope")
            scope = outer.split(":", 1)[1] if outer else None
        module = self.types[context].module.path
        package = self.package_of(context)
        options = [self.imports[module].get(head)] + [f"{package}.{head}" if package else head] + \
            [f"{p}.{head}" for p in self.wildcards[module]]
        for found in options:
            if found and found in self.types:
                return f"{found}.{rest}" if rest and f"{found}.{rest}" in self.types else found
        return None

    # PURPOSE: PROJECT SUPERCLASSES AND INTERFACES OF A CLASS, NEAREST FIRST
    def supertypes(self, fqn: str) -> list[str]:
        found, queue = [], [fqn]
        while queue:
            current = queue.pop(0)
            a = self.types[current].entity.attributes
            for written in a["extends"] + a["implements"]:
                if (parent := self.resolve_type(written, current)) and parent not in found and parent != fqn:
                    found.append(parent)
                    queue.append(parent)
        return found

    # PURPOSE: CLASSES WHOSE MEMBERS AN UNQUALIFIED NAME CAN REACH: THE CLASS, ITS SUPERTYPES, THEN ENCLOSING CLASSES
    def visible(self, fqn: str) -> list[str]:
        found = []
        while fqn:
            found += [fqn, *self.supertypes(fqn)]
            outer = self.types[fqn].entity.attributes.get("scope")
            fqn = outer.split(":", 1)[1] if outer else None
        return found

    # PURPOSE: METHODS NAMED SO, CALLABLE WITH THIS MANY ARGUMENTS, IN THE FIRST CLASS ALONG THE CHAIN THAT HAS ANY
    def methods(self, chain: list[str], name: str, args: int) -> list[Entity]:
        for fqn in chain:
            fits = [m for m in self.types[fqn].methods.get(name, []) if accepts(m, args)]
            if fits:
                return fits
        return []

    # PURPOSE: THE FIELD A NAME MEANS ALONG A CHAIN OF CLASSES
    def field(self, chain: list[str], name: str) -> Entity | None:
        return next((self.types[fqn].fields[name] for fqn in chain if name in self.types[fqn].fields), None)


# PURPOSE: TRUE WHEN A METHOD TAKES THIS MANY ARGUMENTS, COUNTING VARARGS AS ZERO OR MORE
def accepts(method: Entity, args: int | None) -> bool:
    params = method.attributes["params"]
    if args is None:  # a method reference fits any overload
        return True
    if params and params[-1].endswith("..."):
        return args >= len(params) - 1
    return args == len(params)


# PURPOSE: THE CLASS FQN A METHOD, FIELD OR INITIALIZER BELONGS TO
def owner_class(scope: str, entities: dict[str, Entity]) -> str:
    return entities[scope].attributes["scope"].split(":", 1)[1]


# PURPOSE: ADDS JAVA NODES AND EDGES TO A GRAPH BUILDER
def add_java(builder, modules: list[IRModule]) -> None:
    index = JavaIndex(modules)
    entities = {e.id: e for m in modules for e in m.entities}
    for module in modules:
        for e in module.entities:
            if e.kind in ("class", "method", "field"):
                builder.node(e.id, e.kind, e.name, e.provenance, {"module": module.path, "language": "java"})
                if scope := e.attributes.get("scope"):
                    builder.edge(f"contains>{e.id}", scope, e.id, "contains", e.provenance,
                                 anchor=INITIALIZER_WORDS.get(e.name, e.name))
    for fqn, info in index.types.items():
        a = info.entity.attributes
        for kind, names in (("extends", a["extends"]), ("implements", a["implements"])):
            for written in names:
                if parent := index.resolve_type(written, fqn):
                    builder.edge(f"{info.entity.id}>{kind}>{parent}", info.entity.id, f"class:{parent}", kind,
                                 info.entity.provenance, anchor=written.rsplit(".", 1)[-1])
    resolver = CallResolver(index, entities)
    for module in modules:
        for e in module.entities:
            match e.kind:
                case "call":
                    add_call(builder, resolver, e)
                case "field-ref":
                    add_use(builder, index, e, owner_class(e.attributes["scope"], entities))
                case "crypto-call":
                    service = builder.node(f"crypto-service:{e.attributes['service']}", "crypto-service",
                                           e.attributes["service"], e.provenance, {"category": e.attributes["category"]})
                    builder.edge(e.id, e.attributes["scope"], service, "uses-crypto", e.provenance,
                                 category=e.attributes["category"], via="java", anchor=e.name.split(".")[0].removeprefix("new "))


class CallResolver:
    # PURPOSE: RESOLVES CALLS ONCE EACH, SO A CHAINED CALL CAN USE THE RETURN TYPE OF THE CALL BEFORE IT
    def __init__(self, index: JavaIndex, entities: dict[str, Entity]) -> None:
        self.index, self.entities = index, entities
        self.done: dict[str, tuple[list[str] | None, list[Entity]]] = {}

    # PURPOSE: THE CLASSES A CALL MAY LAND IN, FROM ITS RECEIVER, OR NONE WHEN THE RECEIVER'S TYPE IS NOT KNOWN
    def chain(self, e: Entity) -> list[str] | None:
        index, caller = self.index, owner_class(e.attributes["scope"], self.entities)
        receiver, receiver_type = e.attributes["receiver"], e.attributes["receiver_type"]
        if inner := e.attributes.get("receiver_call"):
            found = self.result_type(self.entities[inner])
            return [found, *index.supertypes(found)] if found else None
        if e.name == "<init>":
            if receiver == "super":
                return index.supertypes(caller)[:1]
            if receiver == "this":
                return [caller]
            found = index.resolve_type(receiver_type, caller)
            return [found] if found else None
        if receiver in (None, "this"):
            return index.visible(caller)
        if receiver == "super":
            return index.supertypes(caller)
        found = index.resolve_type(receiver_type, caller)
        return [found, *index.supertypes(found)] if found else None

    # PURPOSE: (CHAIN, TARGET METHODS) OF A CALL, WORKED OUT ONCE
    def resolve(self, e: Entity) -> tuple[list[str] | None, list[Entity]]:
        if e.id not in self.done:
            self.done[e.id] = (None, [])  # a call cannot be its own receiver; this also stops a cycle
            chain = self.chain(e)
            self.done[e.id] = (chain, self.index.methods(chain, e.name, e.attributes["args"]) if chain else [])
        return self.done[e.id]

    # PURPOSE: THE PROJECT CLASS A CALL RETURNS, IF IT RETURNS ONE
    def result_type(self, e: Entity) -> str | None:
        chain, targets = self.resolve(e)
        if e.name == "<init>":
            return chain[0] if chain else None
        if not targets:
            return None
        target = targets[0]
        return self.index.resolve_type(target.attributes["returns"], target.attributes["scope"].split(":", 1)[1])


# PURPOSE: ADDS CALLS EDGES FOR ONE CALL, OR AN UNRESOLVED EDGE WHEN ITS NAME IS A PROJECT METHOD BUT ITS RECEIVER IS UNKNOWN
def add_call(builder, resolver: CallResolver, e: Entity) -> None:
    chain, targets = resolver.resolve(e)
    anchor = (e.attributes["receiver_type"] or e.attributes["receiver"] or e.name).rsplit(".", 1)[-1] \
        if e.name == "<init>" else e.name
    if chain is None:
        if e.name != "<init>" and e.name in resolver.index.method_names:
            builder.unresolved(e.id, e.attributes["scope"], f"method:{e.name}", "calls", e.provenance,
                               "receiver type not known", anchor=anchor)
        return
    if not targets and e.name == "<init>" and chain:
        builder.edge(e.id, e.attributes["scope"], f"class:{chain[0]}", "calls", e.provenance, anchor=anchor)
    extra = {"target_from": "arity"} if len(targets) > 1 else {}
    for n, target in enumerate(targets):
        key = e.id if n == 0 else f"{e.id}>{target.id}"
        builder.edge(key, e.attributes["scope"], target.id, "calls", e.provenance, anchor=anchor, **extra)


# PURPOSE: ADDS A USES-FIELD EDGE FROM THE METHOD OR INITIALIZER TO THE FIELD IT NAMES
def add_use(builder, index: JavaIndex, e: Entity, caller: str) -> None:
    receiver = e.attributes["receiver"]
    if receiver in (None, "this"):
        chain = index.visible(caller)
    else:
        found = index.resolve_type(receiver, caller)
        chain = [found, *index.supertypes(found)] if found else []
    if (target := index.field(chain, e.name)) is not None:
        builder.edge(e.id, e.attributes["scope"], target.id, "uses-field", e.provenance, anchor=e.name)
