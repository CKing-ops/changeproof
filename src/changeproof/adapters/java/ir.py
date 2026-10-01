"""Java source to IR entities with file:line provenance (ROADMAP Week 11), using tree-sitter-java.

Entities: classes (also interfaces, enums, records), methods and constructors, fields, imports, and
inside each method its calls, field uses and JCA crypto calls. Ids are kind plus qualified name;
calls and uses are numbered within the method that holds them. Types are read as written: a call's
receiver type comes from a declared local, parameter or field of the same file, and is resolved
across files by the graph builder.
"""

import re
from collections import Counter
from pathlib import Path

import tree_sitter
import tree_sitter_java

from changeproof.adapters.base import Entity, IRModule
from changeproof.adapters.java.crypto import FACTORY_METHODS, JCA_SERVICES, KEY_SIZE_METHODS, crypto_attributes
from changeproof.provenance import Provenance
from changeproof.signer import digest

PARSER = tree_sitter.Parser(tree_sitter.Language(tree_sitter_java.language()))
TYPE_NODES = {  # RENAME: TREE-SITTER DECLARATION NODE TO THE TYPE KIND RECORDED
    "class_declaration": "class", "interface_declaration": "interface", "enum_declaration": "enum",
    "record_declaration": "record", "annotation_type_declaration": "annotation",
}
COMMENTS = frozenset({"line_comment", "block_comment"})
NOT_A_USE = frozenset({  # RENAME: PARENTS UNDER WHICH AN IDENTIFIER IS NOT A FIELD READ OR WRITE
    "field_access", "method_reference", "labeled_statement", "break_statement", "continue_statement",
    "scoped_identifier", "annotation", "marker_annotation", "inferred_parameters", "lambda_expression",
    "catch_formal_parameter", "resource",
})
DECLARING = ("local_variable_declaration", "formal_parameter", "spread_parameter", "catch_formal_parameter",
             "enhanced_for_statement", "resource", "inferred_parameters", "lambda_expression")
GENERICS = re.compile(r"<[^<>]*>")
ANNOTATION = re.compile(r"@[\w.]+(\([^()]*\))?\s*")


class JavaSyntaxError(ValueError):
    # PURPOSE: KEEPS EACH (WHERE, MESSAGE) PAIR THE PARSER REPORTED
    def __init__(self, errors: list[tuple[Provenance, str]]):
        super().__init__("; ".join(f"{where}: {message}" for where, message in errors))
        self.errors = errors


# PURPOSE: A TYPE AS WRITTEN, WITHOUT ANNOTATIONS, GENERIC ARGUMENTS OR SPACES
def erase(text: str) -> str:
    text = ANNOTATION.sub("", text)
    while GENERICS.search(text):
        text = GENERICS.sub("", text)
    return re.sub(r"\s+", "", text)


# PURPOSE: SHORT DIGEST OF A SUBTREE'S TOKENS, COMMENTS AND LAYOUT IGNORED, SO ONLY REAL EDITS CHANGE IT
def token_digest(node: tree_sitter.Node | None) -> str | None:
    if node is None:
        return None
    tokens, stack = [], [node]
    while stack:
        current = stack.pop()
        if current.type in COMMENTS:
            continue
        if current.child_count == 0:
            tokens.append(current.text.decode())
        stack.extend(reversed(current.children))
    return digest(" ".join(tokens).encode())["sha-384"][:32]


# PURPOSE: FIRST ERROR OR MISSING NODE IN A TREE, IF ANY
def first_error(node: tree_sitter.Node) -> tree_sitter.Node | None:
    stack = [node]
    while stack:
        current = stack.pop()
        if current.is_error or current.is_missing:
            return current
        if current.has_error:
            stack.extend(reversed(current.children))
    return None


class ModuleBuilder:
    # PURPOSE: STARTS ON ONE PARSED FILE
    def __init__(self, source: bytes, rel: str):
        self.source, self.rel = source, rel
        self.package = ""
        self.entities: list[Entity] = []
        self.crypto_names: dict[str, str] = {}  # RENAME: NAME AS WRITTEN TO THE JCA CLASS IT MEANS
        self.fields: dict[str, dict[str, str]] = {}  # RENAME: CLASS FQN TO ITS FIELD NAMES AND TYPES
        self.outer: dict[str, str] = {}  # RENAME: NESTED CLASS FQN TO ITS ENCLOSING CLASS FQN
        self.numbers: Counter = Counter()
        self.calls: list[tuple[tree_sitter.Node, dict]] = []  # RENAME: CALLS SEEN IN THE BODY BEING SCANNED

    # PURPOSE: PROVENANCE OF A NODE: ITS FIRST LINE, AND ITS LAST WHEN IT SPANS SEVERAL
    def where(self, node: tree_sitter.Node) -> Provenance:
        first, last = node.start_point[0] + 1, node.end_point[0] + 1
        return Provenance(file=self.rel, line=first, end_line=last if last != first else None)

    # PURPOSE: ADDS ONE ENTITY
    def add(self, entity_id: str, kind: str, name: str, node: tree_sitter.Node, attributes: dict) -> None:
        self.entities.append(Entity(id=entity_id, kind=kind, name=name, provenance=self.where(node),
                                    attributes=attributes))

    # PURPOSE: NEXT NUMBERED ID FOR A FACT INSIDE A METHOD OR FIELD
    def numbered(self, kind: str, scope: str) -> str:
        self.numbers[kind, scope] += 1
        return f"{kind}:{scope.split(':', 1)[1]}#{self.numbers[kind, scope]}"

    # PURPOSE: READS THE PACKAGE, IMPORTS AND EVERY TOP-LEVEL TYPE
    def build(self, root: tree_sitter.Node, stem: str) -> None:
        for child in root.named_children:
            if child.type == "package_declaration":
                self.package = next(c.text.decode() for c in child.named_children if "identifier" in c.type)
        for child in root.named_children:
            if child.type == "import_declaration":
                self.add_import(child, stem)
            elif child.type in TYPE_NODES:
                self.add_type(child, None)

    # PURPOSE: RECORDS AN IMPORT AND LEARNS WHICH JCA CLASSES IT BRINGS INTO SCOPE
    def add_import(self, node: tree_sitter.Node, stem: str) -> None:
        name = next(c.text.decode() for c in node.named_children if "identifier" in c.type)
        wildcard = any(c.type == "asterisk" for c in node.named_children)
        static = any(c.type == "static" for c in node.children)
        written = name + (".*" if wildcard else "")
        owner = f"{self.package}.{stem}" if self.package else stem
        self.add(f"import:{owner}/{written}", "import", written, node, {"static": static})
        for service in JCA_SERVICES:
            package, simple = service.rsplit(".", 1)
            if (wildcard and name == package) or name == service:
                self.crypto_names[simple] = service

    # PURPOSE: RECORDS A TYPE, ITS FIELDS FIRST SO METHODS CAN SEE THEM, THEN ITS MEMBERS
    def add_type(self, node: tree_sitter.Node, outer: str | None) -> None:
        name = node.child_by_field_name("name").text.decode()
        fqn = f"{outer}.{name}" if outer else f"{self.package}.{name}" if self.package else name
        type_id = f"class:{fqn}"
        if outer:
            self.outer[fqn] = outer
        superclass = node.child_by_field_name("superclass")
        supers = [erase(t.text.decode()) for t in superclass.named_children] if superclass else []
        interfaces = node.child_by_field_name("interfaces") or next(
            (c for c in node.named_children if c.type == "extends_interfaces"), None)
        implemented = [erase(t.text.decode()) for c in interfaces.named_children for t in c.named_children] \
            if interfaces else []
        if TYPE_NODES[node.type] == "interface":
            supers, implemented = implemented, []
        attributes = {"type_kind": TYPE_NODES[node.type], "extends": supers, "implements": implemented,
                      "modifiers": self.modifiers(node)}
        self.add(type_id, "class", name, node, attributes | ({"scope": f"class:{outer}"} if outer else {}))
        body = node.child_by_field_name("body")
        members = list(body.named_children) if body else []
        for part in [m for m in members if m.type == "enum_body_declarations"]:
            members += part.named_children
        components = node.child_by_field_name("parameters")
        self.fields[fqn] = {
            **{c.child_by_field_name("name").text.decode(): erase(c.child_by_field_name("type").text.decode())
               for c in (components.named_children if components else []) if c.type == "formal_parameter"},
            **{d.child_by_field_name("name").text.decode(): erase(m.child_by_field_name("type").text.decode())
               for m in members if m.type in ("field_declaration", "constant_declaration")
               for d in m.children_by_field_name("declarator")},
            **{m.child_by_field_name("name").text.decode(): name for m in members if m.type == "enum_constant"},
        }
        if components:
            self.add_record_components(components, fqn, type_id, members)
        for member in members:
            self.add_member(member, fqn, type_id, name)

    # PURPOSE: MODIFIERS OF A DECLARATION: KEYWORDS, THEN ANNOTATIONS AS WRITTEN, SINCE FRAMEWORKS ACT ON THEM
    @staticmethod
    def modifiers(node: tree_sitter.Node) -> list[str]:
        found = next((c for c in node.children if c.type == "modifiers"), None)
        if found is None:
            return []
        return sorted(c.type for c in found.children if "annotation" not in c.type) + \
            sorted(re.sub(r"\s+", "", c.text.decode()) for c in found.children if "annotation" in c.type)

    # PURPOSE: A RECORD'S COMPONENTS AS FIELDS, AND THEIR ACCESSORS UNLESS THE RECORD WRITES ITS OWN
    def add_record_components(self, components: tree_sitter.Node, fqn: str, type_id: str, members: list) -> None:
        written = {m.child_by_field_name("name").text.decode() for m in members if m.type == "method_declaration"}
        for c in components.named_children:
            if c.type != "formal_parameter":
                continue
            name = c.child_by_field_name("name").text.decode()
            kind = erase(c.child_by_field_name("type").text.decode())
            self.add(f"field:{fqn}.{name}", "field", name, c, {"type": kind, "modifiers": ["final", "private"],
                                                                  "value": None, "scope": type_id})
            if name not in written:
                self.add(f"method:{fqn}.{name}()", "method", name, c,
                         {"params": [], "returns": kind, "modifiers": ["public"], "body": None, "implicit": True,
                          "scope": type_id})

    # PURPOSE: ONE MEMBER OF A TYPE: FIELD, ENUM CONSTANT, METHOD, CONSTRUCTOR, INITIALIZER OR NESTED TYPE
    def add_member(self, node: tree_sitter.Node, fqn: str, type_id: str, simple: str) -> None:
        match node.type:
            case "field_declaration" | "constant_declaration":
                kind = erase(node.child_by_field_name("type").text.decode())
                for d in node.children_by_field_name("declarator"):
                    name, value = d.child_by_field_name("name").text.decode(), d.child_by_field_name("value")
                    field_id = f"field:{fqn}.{name}"
                    self.add(field_id, "field", name, node, {"type": kind, "modifiers": self.modifiers(node),
                                                             "value": token_digest(value), "scope": type_id})
                    if value:
                        self.scan(value, field_id, fqn, set())
            case "enum_constant":
                name = node.child_by_field_name("name").text.decode()
                field_id = f"field:{fqn}.{name}"
                self.add(field_id, "field", name, node, {"type": simple, "modifiers": ["final", "public", "static"],
                                                         "value": token_digest(node), "scope": type_id})
                self.scan(node, field_id, fqn, set())
            case "method_declaration" | "constructor_declaration" | "compact_constructor_declaration":
                self.add_method(node, fqn, type_id, simple)
            case "static_initializer" | "block":
                name = "<clinit>" if node.type == "static_initializer" else "<instance-init>"
                method_id = f"method:{fqn}.{name}()"
                self.add(method_id, "method", name, node, {"params": [], "returns": None, "modifiers": [],
                                                           "body": token_digest(node), "scope": type_id})
                self.scan(node, method_id, fqn, set())
            case kind if kind in TYPE_NODES:
                self.add_type(node, fqn)

    # PURPOSE: A METHOD OR CONSTRUCTOR, ITS SIGNATURE FROM THE DECLARED PARAMETER TYPES, THEN ITS BODY
    def add_method(self, node: tree_sitter.Node, fqn: str, type_id: str, simple: str) -> None:
        constructor = node.type != "method_declaration"
        name = "<init>" if constructor else node.child_by_field_name("name").text.decode()
        params, local_types = [], {}
        if node.type == "compact_constructor_declaration":
            params = list(self.fields[fqn].values())
        for p in (node.child_by_field_name("parameters").named_children if not params else []):
            if p.type == "formal_parameter":
                kind, names = erase(p.child_by_field_name("type").text.decode()), [p.child_by_field_name("name")]
            elif p.type == "spread_parameter":
                kind = erase(next(c for c in p.named_children if c.type not in ("modifiers", "variable_declarator")).text.decode()) + "..."
                names = [d.child_by_field_name("name") for d in p.named_children if d.type == "variable_declarator"]
            else:
                continue
            params.append(kind)
            local_types.update({n.text.decode(): kind.removesuffix("...") for n in names})
        method_id = f"method:{fqn}.{name}({','.join(params)})"
        body = node.child_by_field_name("body")
        returns = node.child_by_field_name("type")
        throws = next((c for c in node.named_children if c.type == "throws"), None)
        self.add(method_id, "method", simple if constructor else name, node,
                 {"params": params, "returns": erase(returns.text.decode()) if returns else None,
                  "throws": sorted(erase(t.text.decode()) for t in throws.named_children) if throws else [],
                  "modifiers": self.modifiers(node), "body": token_digest(body), "scope": type_id})
        if body:
            self.scan(body, method_id, fqn, set(local_types), local_types)

    # PURPOSE: TYPE OF A FIELD VISIBLE FROM A CLASS IN THIS FILE, LOOKING OUTWARD THROUGH ENCLOSING CLASSES
    def field_type(self, fqn: str, name: str) -> str | None:
        while fqn:
            if name in self.fields.get(fqn, {}):
                return self.fields[fqn][name]
            fqn = self.outer.get(fqn)
        return None

    # PURPOSE: RECORDS THE CALLS, FIELD USES AND CRYPTO CALLS INSIDE A METHOD BODY OR FIELD INITIALIZER
    def scan(self, body: tree_sitter.Node, scope: str, fqn: str, local_names: set[str],
             local_types: dict[str, str] | None = None) -> None:
        local_types = dict(local_types or {})
        nodes, stack = [], [body]
        while stack:
            node = stack.pop()
            if node.type in COMMENTS:
                continue
            nodes.append(node)
            stack.extend(reversed(node.named_children))
        for node in nodes:
            if node.type in DECLARING:
                local_names.update(self.declared(node, local_types))
        pending: dict[int, dict] = {}  # RENAME: CRYPTO CALL NODE ID TO ITS ENTITY FIELDS, FILLED BEFORE IT IS ADDED
        by_variable: dict[str, dict] = {}  # RENAME: LOCAL NAME TO THE CRYPTO CALL ASSIGNED TO IT
        self.calls = []
        for node in nodes:
            match node.type:
                case "method_invocation":
                    self.invocation(node, scope, fqn, local_names, local_types, pending, by_variable)
                case "object_creation_expression":
                    kind = erase(node.child_by_field_name("type").text.decode())
                    service = self.jca(kind)
                    if service == "java.security.SecureRandom":
                        pending[node.id] = {"node": node, "name": f"new {kind}",
                                            "attributes": crypto_attributes(service, None, None)}
                    else:
                        self.add_call(node, scope, "<init>", None, kind, node.child_by_field_name("arguments"))
                case "explicit_constructor_invocation":
                    keyword = node.child_by_field_name("constructor").text.decode()
                    self.add_call(node, scope, "<init>", keyword, None, node.child_by_field_name("arguments"))
                case "field_access":
                    owner, field = node.child_by_field_name("object"), node.child_by_field_name("field").text.decode()
                    written = owner.text.decode()
                    if written == "this" or (owner.type == "identifier" and written[:1].isupper()
                                              and written not in local_names and not self.field_type(fqn, written)):
                        self.add_use(node, scope, field, written)
                case "identifier" if self.is_field_use(node, fqn, local_names):
                    self.add_use(node, scope, node.text.decode(), None)
                case "method_reference":
                    self.reference(node, scope, fqn, local_names, local_types, pending)
        # a call made on the result of another call names it, so the graph can follow its return type
        ids = {node.id: self.numbered("call", scope) for node, _ in self.calls}
        for node, attributes in self.calls:
            owner = node.child_by_field_name("object")
            if owner is not None and owner.id in ids:
                attributes["receiver_call"] = ids[owner.id]
            self.add(ids[node.id], "call", attributes.pop("name"), node, attributes)
        for found in sorted(pending.values(), key=lambda p: p["node"].start_byte):
            self.add(self.numbered("crypto-call", scope), "crypto-call", found["name"], found["node"],
                     found["attributes"] | {"scope": scope})

    # PURPOSE: NAMES A DECLARATION INTRODUCES, NOTING THE DECLARED TYPE OF EACH
    @staticmethod
    def declared(node: tree_sitter.Node, local_types: dict[str, str]) -> set[str]:
        kind = node.child_by_field_name("type")
        written = erase(kind.text.decode()) if kind else None
        names = set()
        if node.type == "local_variable_declaration":
            for d in node.children_by_field_name("declarator"):
                name = d.child_by_field_name("name").text.decode()
                value = d.child_by_field_name("value")
                if written == "var" and value is not None and value.type == "object_creation_expression":
                    local_types[name] = erase(value.child_by_field_name("type").text.decode())
                elif written != "var":
                    local_types[name] = written
                names.add(name)
        elif node.type == "inferred_parameters":
            names |= {c.text.decode() for c in node.named_children}
        elif node.type == "lambda_expression":
            params = node.child_by_field_name("parameters")
            if params is not None and params.type == "identifier":
                names.add(params.text.decode())
        elif (name := node.child_by_field_name("name")) is not None:
            names.add(name.text.decode())
            if written:
                local_types[name.text.decode()] = written
        return names

    # PURPOSE: TRUE WHEN A BARE IDENTIFIER READS OR WRITES A FIELD OF THIS FILE RATHER THAN A LOCAL
    def is_field_use(self, node: tree_sitter.Node, fqn: str, local_names: set[str]) -> bool:
        parent = node.parent
        name = node.text.decode()
        if parent is None or parent.type in NOT_A_USE or name in local_names:
            return False
        if node in (parent.child_by_field_name("name"), parent.child_by_field_name("type")):
            return False
        if parent.type == "method_invocation" and parent.child_by_field_name("object") == node:
            return False  # the call records it, with the field's type as the receiver type
        return self.field_type(fqn, name) is not None

    # PURPOSE: THE JCA CLASS A TYPE AS WRITTEN NAMES, IF ANY
    def jca(self, written: str) -> str | None:
        return written if written in JCA_SERVICES else self.crypto_names.get(written)

    # PURPOSE: A METHOD CALL: A JCA FACTORY BECOMES A CRYPTO CALL, A KEY SIZE IS NOTED, ANYTHING ELSE IS A CALL
    def invocation(self, node, scope, fqn, local_names, local_types, pending, by_variable) -> None:
        name = node.child_by_field_name("name").text.decode()
        owner = node.child_by_field_name("object")
        args = node.child_by_field_name("arguments")
        written = owner.text.decode() if owner else None
        if owner is not None and name in FACTORY_METHODS and (service := self.jca(written)):
            literal = next((a.text.decode()[1:-1] for a in args.named_children if a.type == "string_literal"), None)
            pending[node.id] = {"node": node, "name": f"{written.rsplit('.', 1)[-1]}.{name}", "literal": literal,
                                "attributes": crypto_attributes(service, literal, None)}
            if node.parent.type == "variable_declarator":
                by_variable[node.parent.child_by_field_name("name").text.decode()] = pending[node.id]
            return
        if owner is not None and owner.type == "identifier" and name in KEY_SIZE_METHODS and written in by_variable:
            bits = next((int(a.text.decode()) for a in args.named_children if a.type == "decimal_integer_literal"), None)
            found = by_variable[written]
            found["attributes"] = crypto_attributes(found["attributes"]["service"], found.get("literal"), bits)
        receiver_type = None
        if owner is not None and owner.type == "identifier":
            if written in local_names:
                receiver_type = local_types.get(written)
            elif kind := self.field_type(fqn, written):
                receiver_type = kind
                self.add_use(owner, scope, written, None)
            elif written[:1].isupper():
                receiver_type = written
        elif owner is not None and owner.type == "field_access" and owner.child_by_field_name("object").text == b"this":
            receiver_type = self.field_type(fqn, owner.child_by_field_name("field").text.decode())
        elif owner is not None and owner.type == "scoped_identifier":
            receiver_type = written
        self.add_call(node, scope, name, written, receiver_type, args)

    # PURPOSE: A METHOD REFERENCE: A JCA CONSTRUCTOR OR FACTORY IS A CRYPTO CALL, ANYTHING ELSE A CALL OF ANY ARITY
    def reference(self, node, scope, fqn, local_names, local_types, pending) -> None:
        owner, target = node.named_children[0], node.children[-1]
        written, name = owner.text.decode(), target.text.decode()
        service = self.jca(erase(written))
        if service and (name in FACTORY_METHODS or (name == "new" and service == "java.security.SecureRandom")):
            pending[node.id] = {"node": node, "name": f"{written}::{name}", "attributes": crypto_attributes(service, None, None)}
            return
        if written in ("this", "super"):
            receiver_type = None
        elif written in local_names:
            receiver_type = local_types.get(written)
        else:
            receiver_type = self.field_type(fqn, written) or erase(written)
        self.add_call(node, scope, "<init>" if name == "new" else name, written, receiver_type, None)

    # PURPOSE: QUEUES A CALL FACT; SCAN NUMBERS AND ADDS IT ONCE IT KNOWS WHICH CALL PRODUCED ITS RECEIVER
    def add_call(self, node, scope: str, name: str, receiver: str | None, receiver_type: str | None, args) -> None:
        self.calls.append((node, {"name": name, "receiver": receiver, "receiver_type": receiver_type,
                                  "args": len(args.named_children) if args else None if node.type == "method_reference"
                                  else 0, "scope": scope}))

    # PURPOSE: ADDS A FIELD-USE FACT
    def add_use(self, node, scope: str, field: str, receiver: str | None) -> None:
        self.add(self.numbered("field-ref", scope), "field-ref", field, node,
                 {"field": field, "receiver": receiver, "scope": scope})


# PURPOSE: PARSES ONE JAVA FILE INTO AN IR MODULE, REFUSING A FILE THE GRAMMAR CANNOT READ
def parse_java(path: Path, root: Path) -> IRModule:
    rel = Path(path).resolve().relative_to(Path(root).resolve()).as_posix()
    source = Path(path).read_bytes()
    tree = PARSER.parse(source)
    if bad := first_error(tree.root_node):
        message = f"missing {bad.type}" if bad.is_missing else f"cannot parse '{bad.text.decode()[:40]}'"
        raise JavaSyntaxError([(Provenance(file=rel, line=bad.start_point[0] + 1), message)])
    builder = ModuleBuilder(source, rel)
    builder.build(tree.root_node, Path(path).stem)
    return IRModule(path=rel, language="java", entities=builder.entities)
