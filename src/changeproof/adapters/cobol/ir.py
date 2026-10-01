"""Turns a Cobol85 parse tree into IR entities, each with file:line provenance.

Entity ids are built from names, never line numbers, so moving code does not change them. Where
a name can repeat (copybooks, calls), an ordinal in source order keeps the id unique.
"""

import re
from collections import Counter

from antlr4 import ParserRuleContext

from changeproof.adapters.base import Entity
from changeproof.adapters.cobol._generated.Cobol85Parser import Cobol85Parser as P
from changeproof.adapters.cobol.crypto import classify_call, classify_sql
from changeproof.adapters.cobol.preprocess import Source
from changeproof.provenance import Provenance

DATA_SECTIONS = {  # RENAME: PARSE-TREE SECTION TYPE TO THE SECTION NAME STORED ON DATA ITEMS
    P.FileSectionContext: "file",
    P.WorkingStorageSectionContext: "working-storage",
    P.LocalStorageSectionContext: "local-storage",
    P.LinkageSectionContext: "linkage",
}
CICS_OPTIONS = {  # RENAME: CICS OPTION NAMES TO THE ATTRIBUTE THEY FILL (LITERAL) OR ITS _REF (DATA NAME)
    "program": "PROGRAM", "file": "FILE|DATASET", "transid": "TRANSID", "map": "MAP", "mapset": "MAPSET",
}
CICS_OPERAND_RE = {
    attribute: re.compile(rf"\b(?:{words})\s*\(\s*(?:'([^']*)'|\"([^\"]*)\"|([\w-]+)(?:\s*\([^)]*\))?)\s*\)",
                          re.IGNORECASE)
    for attribute, words in CICS_OPTIONS.items()
}



# PURPOSE: SPLITS A DATA-FLOW STATEMENT INTO (VERB, SENDING PARTS, RECEIVING PARTS), OR NONE FOR OTHER NODES
def flow_parts(node: ParserRuleContext) -> tuple[str, list, list] | None:
    match node:
        case P.MoveToStatementContext():
            return "MOVE", [node.moveToSendingArea()], node.identifier()
        case P.MoveCorrespondingToStatementContext():
            return "MOVE", [node.moveCorrespondingToSendingArea()], node.identifier()
        case P.ComputeStatementContext():
            return "COMPUTE", [node.arithmeticExpression()], node.computeStore()
        case P.AddToStatementContext():
            return "ADD", node.addFrom(), node.addTo()
        case P.AddToGivingStatementContext():
            return "ADD", node.addFrom() + node.addToGiving(), node.addGiving()
        case P.AddCorrespondingStatementContext():
            return "ADD", [node.identifier()], [node.addTo()]
        case P.SubtractFromStatementContext():
            return "SUBTRACT", node.subtractSubtrahend(), node.subtractMinuend()
        case P.SubtractFromGivingStatementContext():
            return "SUBTRACT", node.subtractSubtrahend() + [node.subtractMinuendGiving()], node.subtractGiving()
        case P.SubtractCorrespondingStatementContext():
            return "SUBTRACT", [node.qualifiedDataName()], [node.subtractMinuendCorresponding()]
        case P.MultiplyStatementContext():
            first = node.identifier() or node.literal()
            if regular := node.multiplyRegular():
                return "MULTIPLY", [first], regular.multiplyRegularOperand()
            giving = node.multiplyGiving()
            return "MULTIPLY", [first, giving.multiplyGivingOperand()], giving.multiplyGivingResult()
        case P.DivideStatementContext():
            return divide_parts(node)
        case P.ReadStatementContext() if node.readInto():
            return "READ", [], [node.readInto().identifier()]
        case P.WriteStatementContext() if node.writeFromPhrase():
            return "WRITE", [node.writeFromPhrase()], [node.recordName()]
        case P.RewriteStatementContext() if node.rewriteFrom():
            return "REWRITE", [node.rewriteFrom()], [node.recordName()]
        case P.StringStatementContext():
            return "STRING", [s for p in node.stringSendingPhrase() for s in p.stringSending()], \
                [node.stringIntoPhrase().identifier()]
        case P.UnstringStatementContext():
            return "UNSTRING", [node.unstringSendingPhrase().identifier()], \
                [i.identifier() for i in node.unstringIntoPhrase().unstringInto()]
    return None


# PURPOSE: SENDING AND RECEIVING PARTS OF THE FOUR DIVIDE FORMATS, REMAINDER INCLUDED
def divide_parts(node: P.DivideStatementContext) -> tuple[str, list, list]:
    first = node.identifier() or node.literal()
    remainder = [node.divideRemainder().identifier()] if node.divideRemainder() else []
    if into := node.divideIntoStatement():
        return "DIVIDE", [first], into.divideInto() + remainder
    other = node.divideIntoGivingStatement() or node.divideByGivingStatement()
    giving = other.divideGivingPhrase().divideGiving() if other.divideGivingPhrase() else []
    return "DIVIDE", [first, other.identifier() or other.literal()], giving + remainder


# PURPOSE: DATA NAMES A STATEMENT PART REFERS TO, AS "NAME" OR "NAME OF GROUP"; SUBSCRIPTS ARE NOT FOLLOWED
def data_refs(ctx: ParserRuleContext) -> list[str]:
    found = []
    stack = [ctx]
    while stack:
        node = stack.pop()
        if not isinstance(node, ParserRuleContext):
            continue
        if isinstance(node, P.IdentifierContext) and node.specialRegister():
            continue
        if isinstance(node, P.QualifiedDataNameContext):
            found.append(qualified_name(node))
            continue
        stack.extend(reversed(node.children or []))
    return found


# PURPOSE: RENDERS A QUALIFIED DATA NAME AS "NAME OF GROUP OF RECORD"
def qualified_name(node: P.QualifiedDataNameContext) -> str:
    format1 = node.qualifiedDataNameFormat1()
    if format1 is None:
        return node.getText().upper()
    parts = [(format1.dataName() or format1.conditionName()).getText().upper()]
    for qualifier in format1.qualifiedInData():
        if data := qualifier.inData():
            parts.append(data.dataName().getText().upper())
        else:
            parts.append(qualifier.inTable().tableCall().qualifiedDataName().getText().upper())
    if in_file := format1.inFile():
        parts.append(in_file.fileName().getText().upper())
    return " OF ".join(parts)


class Builder:
    # PURPOSE: HOLDS THE SOURCE, TOKENS AND RUNNING STATE WHILE ONE MODULE IS WALKED
    def __init__(self, source: Source, tokens) -> None:
        self.source = source
        self.tokens = tokens
        self.entities: list[Entity] = []
        self.seen: Counter[str] = Counter()  # RENAME: HOW MANY TIMES EACH BASE ID HAS BEEN USED
        self.program = ""  # RENAME: NAME OF THE PROGRAM BEING WALKED
        self.section_id: str | None = None
        self.paragraph_id: str | None = None
        self.data_section = ""
        self.levels: list[tuple[int, str, str]] = []  # RENAME: OPEN DATA GROUPS AS (LEVEL, PATH, ID)
        self.values: dict[str, tuple[str, str]] = {}  # RENAME: DATA NAME TO (LITERAL VALUE, ENTITY ID)
        self.paragraph_spans: list[tuple[int, int, str]] = []

    # PURPOSE: PROVENANCE FOR A CONTEXT, WITH AN END LINE WHEN IT ENDS IN THE SAME FILE
    def span(self, ctx: ParserRuleContext) -> Provenance:
        first = self.source.lines[ctx.start.line - 1]
        last = self.source.lines[ctx.stop.line - 1] if ctx.stop is not None else first
        end = first.end_line
        if last.file == first.file and last.line >= first.line:
            end = last.end_line or last.line
        return Provenance(file=first.file, line=first.line, end_line=end if end != first.line else None)

    # PURPOSE: DEFAULT-CHANNEL TOKEN TEXT OF A CONTEXT, SPACE-SEPARATED, SO LINE LAYOUT DOES NOT COUNT
    def text(self, ctx: ParserRuleContext) -> str:
        return " ".join(t.text.strip() for t in self.tokens.tokens[ctx.start.tokenIndex:ctx.stop.tokenIndex + 1]
                        if t.channel == 0 and t.text.strip())

    # PURPOSE: ADDS AN ENTITY, NUMBERING IDS THAT WOULD OTHERWISE REPEAT
    def add(self, kind: str, qualified: str, name: str, provenance: Provenance, attributes: dict,
            numbered: bool = False) -> str:
        base = f"{kind}:{qualified}"
        self.seen[base] += 1
        if numbered:
            entity_id = f"{base}#{self.seen[base]}"
        else:
            entity_id = base if self.seen[base] == 1 else f"{base}#{self.seen[base]}"
        self.entities.append(Entity(id=entity_id, kind=kind, name=name, provenance=provenance,
                                    attributes=attributes))
        return entity_id

    # PURPOSE: QUALIFIED NAME OF THE CURRENT PARAGRAPH OR, OUTSIDE ONE, THE PROGRAM
    def owner(self) -> str:
        return self.paragraph_id.split(":", 1)[1] if self.paragraph_id else self.program

    # PURPOSE: WALKS THE TREE DEPTH-FIRST, HANDLING EACH CONTEXT TYPE THE IR CARES ABOUT
    def walk(self, ctx) -> None:
        stack = [(ctx, False)]
        while stack:
            node, done = stack.pop()
            if not isinstance(node, ParserRuleContext):
                continue
            if done:
                self.leave(node)
                continue
            self.enter(node)
            stack.append((node, True))
            stack.extend((child, False) for child in reversed(node.children or []))

    # PURPOSE: DISPATCHES A CONTEXT ON THE WAY DOWN
    def enter(self, node: ParserRuleContext) -> None:
        match node:
            case P.ProgramUnitContext():
                self.program = node.identificationDivision().programIdParagraph().programName().getText().upper()
                self.add("program", self.program, self.program, self.span(node), {})
            case P.ProcedureSectionContext():
                name = node.procedureSectionHeader().sectionName().getText().upper()
                self.section_id = self.add("section", f"{self.program}.{name}", name, self.span(node), {})
            case P.ParagraphContext():
                self.enter_paragraph(node)
            case _ if type(node) in DATA_SECTIONS:
                self.data_section = DATA_SECTIONS[type(node)]
                self.levels = []
            case P.DataDescriptionEntryFormat1Context() | P.DataDescriptionEntryFormat2Context():
                self.enter_data(node)
            case P.DataDescriptionEntryFormat3Context():
                self.enter_condition(node)
            case P.FileControlEntryContext():
                self.enter_file(node)
            case P.CallStatementContext():
                self.enter_call(node)
            case P.PerformProcedureStatementContext():
                self.enter_perform(node)
            case P.GoToStatementSimpleContext():
                self.add_jump("goto", node.procedureName(), node)
            case P.GoToDependingOnStatementContext():
                for target in node.procedureName():
                    self.add_jump("goto", target, node)
            case _ if parts := flow_parts(node):
                self.add_flow(node, *parts)

    # PURPOSE: CLOSES THE SECTION OR PARAGRAPH SCOPE ON THE WAY BACK UP
    def leave(self, node: ParserRuleContext) -> None:
        if isinstance(node, P.ParagraphContext):
            self.paragraph_spans.append((node.start.line - 1, node.stop.line - 1, self.paragraph_id))
            self.paragraph_id = None
        elif isinstance(node, P.ProcedureSectionContext):
            self.section_id = None

    # PURPOSE: RECORDS A PARAGRAPH WITH ITS NORMALIZED BODY TEXT
    def enter_paragraph(self, node: P.ParagraphContext) -> None:
        name = node.paragraphName().getText().upper()
        scope = self.section_id.split(":", 1)[1] if self.section_id else self.program
        attributes = {"text": self.text(node)}
        if self.section_id:
            attributes["section"] = self.section_id
        self.paragraph_id = self.add("paragraph", f"{scope}.{name}", name, self.span(node), attributes)

    # PURPOSE: RECORDS A DATA ITEM AND ITS PLACE IN THE GROUP HIERARCHY
    def enter_data(self, node) -> None:
        level_text = node.start.text
        level = int(level_text)
        named = node.dataName()
        name = named.getText().upper() if named else "FILLER"
        if level in (1, 77):
            self.levels = []
        while self.levels and self.levels[-1][0] >= level and level != 66:
            self.levels.pop()
        parent_path, parent_id = (self.levels[-1][1], self.levels[-1][2]) if self.levels else (self.program, None)
        attributes = {"level": level_text.zfill(2), "section": self.data_section, "text": self.text(node)}
        if parent_id:
            attributes["parent"] = parent_id
        literal = None  # RENAME: QUOTED VALUE, KEPT SO A DYNAMIC CALL THROUGH THIS ITEM CAN BE RESOLVED
        if isinstance(node, P.DataDescriptionEntryFormat1Context):
            if pic := node.dataPictureClause():
                attributes["picture"] = pic[0].pictureString().getText().upper()
            if value := node.dataValueClause():
                literal = re.search(r"'([^']*)'|\"([^\"]*)\"", self.text(value[0]))
        if literal:
            attributes["value"] = next(g for g in literal.groups() if g is not None)
        entity_id = self.add("data", f"{parent_path}.{name}", name, self.span(node), attributes)
        if literal:
            self.values[name] = (attributes["value"], entity_id)
        if level not in (66, 77):
            self.levels.append((level, entity_id.split(":", 1)[1], entity_id))

    # PURPOSE: RECORDS AN 88-LEVEL CONDITION UNDER THE DATA ITEM IT BELONGS TO
    def enter_condition(self, node: P.DataDescriptionEntryFormat3Context) -> None:
        name = node.conditionName().getText().upper()
        parent_path, parent_id = (self.levels[-1][1], self.levels[-1][2]) if self.levels else (self.program, None)
        attributes = {"text": self.text(node)}
        if parent_id:
            attributes["parent"] = parent_id
        self.add("condition", f"{parent_path}.{name}", name, self.span(node), attributes)

    # PURPOSE: RECORDS A SELECT ENTRY AND WHAT IT IS ASSIGNED TO
    def enter_file(self, node: P.FileControlEntryContext) -> None:
        name = node.selectClause().fileName().getText().upper()
        attributes = {"text": self.text(node)}
        for clause in node.fileControlClause():
            if assign := clause.assignClause():
                attributes["assign"] = " ".join(self.text(assign).split()[1:]).removeprefix("TO ").strip("'\"")
        self.add("file", f"{self.program}.{name}", name, self.span(node), attributes)

    # PURPOSE: RECORDS A CALL, TAGGING IT AS A CRYPTO CALL WHEN IT REACHES A CRYPTO SERVICE
    def enter_call(self, node: P.CallStatementContext) -> None:
        written = (node.literal() or node.identifier()).getText()
        dynamic = node.literal() is None
        target, target_from = written.strip("'\"").upper(), None
        if dynamic and written.upper() in self.values:
            target, target_from = self.values[written.upper()][0].upper(), self.values[written.upper()][1]
        paragraph = {"paragraph": self.paragraph_id} if self.paragraph_id else {}
        if crypto := classify_call(target):
            service, category = crypto
            attributes = {"service": service, "category": category, "via": "call", "dynamic": dynamic}
            if target_from:
                attributes["target_from"] = target_from
            self.add("crypto-call", f"{self.owner()}.{service}", written.upper().strip("'\""),
                     self.span(node), attributes | paragraph, numbered=True)
            return
        attributes = {"target": target, "dynamic": dynamic}
        if target_from:
            attributes["target_from"] = target_from
        self.add("call", f"{self.owner()}.{target}", written.upper().strip("'\""), self.span(node),
                 attributes | paragraph, numbered=True)

    # PURPOSE: RECORDS A PERFORM OF A PARAGRAPH OR SECTION, WITH ITS THRU END IF ANY
    def enter_perform(self, node: P.PerformProcedureStatementContext) -> None:
        targets = node.procedureName()
        thru = {"thru": (targets[1].paragraphName() or targets[1].sectionName()).getText().upper()} if len(targets) > 1 else {}
        self.add_jump("perform", targets[0], node, thru)

    # PURPOSE: ADDS A PERFORM OR GO TO ENTITY NAMING ITS TARGET AS WRITTEN
    def add_jump(self, kind: str, target: P.ProcedureNameContext, node: ParserRuleContext, extra: dict | None = None) -> None:
        para = target.paragraphName()
        name = (para or target.sectionName()).getText().upper()
        attributes = {"target": name} | (extra or {})
        if para and target.inSection():
            attributes["in_section"] = target.inSection().sectionName().getText().upper()
        if self.paragraph_id:
            attributes["paragraph"] = self.paragraph_id
        self.add(kind, f"{self.owner()}.{name}", name, self.span(node), attributes, numbered=True)

    # PURPOSE: RECORDS WHICH FIELDS A STATEMENT READS AND WHICH IT WRITES, NAMED AFTER ITS FIRST TARGET
    def add_flow(self, node: ParserRuleContext, verb: str, sending: list, receiving: list) -> None:
        targets = [name for part in receiving for name in data_refs(part)]
        if not targets:
            return
        attributes = {"verb": verb, "sources": [name for part in sending for name in data_refs(part)],
                      "targets": targets, "text": self.text(node)}
        if isinstance(node, P.ReadStatementContext):
            attributes["file"] = node.fileName().getText().upper()
        if isinstance(node, P.MoveCorrespondingToStatementContext):
            attributes["corresponding"] = True
        if isinstance(node, P.MoveToStatementContext) and (literal := sending[0].literal()) is not None:
            attributes["literal"] = literal.getText().strip("'\"")
        if self.paragraph_id:
            attributes["paragraph"] = self.paragraph_id
        self.add("flow", f"{self.owner()}.{targets[0].split()[0]}", verb, self.span(node), attributes, numbered=True)

    # PURPOSE: ADDS ENTITIES FOR COPY STATEMENTS AND EXEC BLOCKS, WHICH THE PREPROCESSOR HELD
    def add_preprocessed(self) -> None:
        for copy in self.source.copies:
            where = Provenance(file=copy.file, line=copy.line, end_line=copy.end_line)
            self.add("copybook", f"{self.program}.{copy.name}", copy.name, where,
                     {"resolved": copy.resolved, "problem": copy.problem,
                      "replacing": [list(pair) for pair in copy.replacing]}, numbered=True)
        for block in self.source.execs:
            paragraph = next((pid for lo, hi, pid in self.paragraph_spans if lo <= block.index <= hi), None)
            owner = paragraph.split(":", 1)[1] if paragraph else self.program
            where = Provenance(file=block.file, line=block.line,
                               end_line=block.end_line if block.end_line != block.line else None)
            attributes = {"text": block.text, "command": block.text.split(" ", 1)[0].upper() if block.text else ""}
            if paragraph:
                attributes["paragraph"] = paragraph
            if block.kind == "CICS":
                for option, pattern in CICS_OPERAND_RE.items():
                    if m := pattern.search(block.text):
                        literal = m.group(1) if m.group(1) is not None else m.group(2)
                        if literal is not None:
                            attributes[option] = literal.strip().upper()
                        else:
                            attributes[f"{option}_ref"] = m.group(3).upper()
            self.add(f"exec-{block.kind.lower()}", owner, block.kind, where, attributes, numbered=True)
            if block.kind == "SQL":
                for function, category in classify_sql(block.text):
                    extra = {"paragraph": paragraph} if paragraph else {}
                    self.add("crypto-call", f"{owner}.{function}", function, where,
                             {"service": function, "category": category, "via": "sql", "dynamic": False} | extra,
                             numbered=True)


# PURPOSE: BUILDS THE ENTITY LIST FOR ONE PARSED PROGRAM
def build_entities(source: Source, tree, tokens) -> list[Entity]:
    builder = Builder(source, tokens)
    builder.walk(tree)
    builder.add_preprocessed()
    return builder.entities
