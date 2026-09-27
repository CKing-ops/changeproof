"""Reads the why of a change from its commit message: trailers, ticket IDs and people named in trailers.

Ticket IDs are only ever copied from the message. ServiceNow numbers are distinctive enough to be
taken from anywhere. Jira-style keys (PROJ-123) are taken from trailer values, from the start of
the subject, or from square brackets, because the same shape shows up in standard names such as
ISO-27001 or SHA-256.
"""

import re
from dataclasses import dataclass

from changeproof.provenance import Provenance

TRAILER_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9-]*):[ \t]+(\S.*)$")
PERSON_RE = re.compile(r"^(.*?)\s*<([^<>@\s]+@[^<>\s]+)>$")
SERVICENOW_RE = re.compile(r"\b(CHG|CTASK|INC|PRB|RITM|REQ)\d{7}\b")
JIRA_KEY = r"[A-Z][A-Z0-9]{1,9}-[1-9]\d*"
JIRA_RE = re.compile(rf"\b{JIRA_KEY}\b")
JIRA_SUBJECT_RE = re.compile(rf"^\[?({JIRA_KEY})\]?[:\s]")
JIRA_BRACKET_RE = re.compile(rf"\[({JIRA_KEY})\]")
SERVICENOW_TYPES = {  # RENAME: SERVICENOW NUMBER PREFIX TO RECORD TYPE
    "CHG": "change", "CTASK": "change-task", "INC": "incident", "PRB": "problem", "RITM": "request-item",
    "REQ": "request",
}
PERSON_TRAILERS = frozenset({  # RENAME: TRAILERS WHOSE VALUE NAMES A PERSON, SO NO TICKET IS READ FROM THEM
    "requested-by", "approved-by", "reviewed-by", "signed-off-by", "co-authored-by", "acked-by", "tested-by",
})


@dataclass(frozen=True)
class Trailer:
    key: str
    value: str
    provenance: Provenance


@dataclass(frozen=True)
class TicketRef:
    id: str
    system: str  # servicenow or jira
    type: str
    found_in: str  # trailer, subject or body
    provenance: Provenance


# PURPOSE: THE TRAILER BLOCK: THE LAST PARAGRAPH OF THE MESSAGE WHEN EVERY LINE IN IT IS KEY: VALUE
def trailers(message: list[tuple[str, Provenance]]) -> list[Trailer]:
    blanks = [i for i, (text, _) in enumerate(message) if not text.strip()]
    if not blanks:
        return []
    block = message[blanks[-1] + 1:]
    matches = [TRAILER_RE.match(text) for text, _ in block]
    if not block or not all(matches):
        return []
    return [Trailer(m.group(1), m.group(2).strip(), where) for m, (_, where) in zip(matches, block)]


# PURPOSE: SPLITS "NAME <EMAIL>" INTO ITS PARTS; A BARE NAME KEEPS NO EMAIL
def person(value: str) -> tuple[str, str | None]:
    m = PERSON_RE.match(value.strip())
    return (m.group(1).strip(), m.group(2)) if m else (value.strip(), None)


# PURPOSE: TICKET IDS NAMED IN THE MESSAGE, TRAILERS FIRST, EACH ID ONCE
def tickets(message: list[tuple[str, Provenance]], found: list[Trailer]) -> list[TicketRef]:
    refs: dict[str, TicketRef] = {}

    # PURPOSE: KEEPS THE FIRST PLACE AN ID IS SEEN
    def keep(ticket_id: str, system: str, kind: str, where: str, provenance: Provenance) -> None:
        refs.setdefault(ticket_id, TicketRef(ticket_id, system, kind, where, provenance))

    for t in found:
        if t.key.lower() in PERSON_TRAILERS:
            continue
        for m in SERVICENOW_RE.finditer(t.value):
            keep(m.group(0), "servicenow", SERVICENOW_TYPES[m.group(1)], "trailer", t.provenance)
        for m in JIRA_RE.finditer(t.value):
            if not SERVICENOW_RE.fullmatch(m.group(0)):
                keep(m.group(0), "jira", "issue", "trailer", t.provenance)
    trailer_lines = {t.provenance for t in found}
    for index, (text, where) in enumerate(message):
        if where in trailer_lines:
            continue
        place = "subject" if index == 0 else "body"
        for m in SERVICENOW_RE.finditer(text):
            keep(m.group(0), "servicenow", SERVICENOW_TYPES[m.group(1)], place, where)
        jira = JIRA_BRACKET_RE.findall(text)
        if index == 0 and (m := JIRA_SUBJECT_RE.match(text)):
            jira.insert(0, m.group(1))
        for key in jira:
            keep(key, "jira", "issue", place, where)
    return list(refs.values())
