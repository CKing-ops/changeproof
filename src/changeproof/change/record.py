"""Change records: who, what, when, where, how and why for one commit (ROADMAP Week 4).

Every field is copied or derived from the repository: the commit object, its diff, and the code on
each side of it. Anything the repository does not say, such as a missing approver or ticket, is
recorded as missing, never filled in.
"""

import os
import re
import tempfile
from collections.abc import Mapping
from pathlib import Path, PurePosixPath

from pydantic import BaseModel, ConfigDict

from changeproof.adapters.base import EntityChange, IRModule, diff_by_id
from changeproof.adapters.cobol import CobolAdapter
from changeproof.adapters.cobol.parse import CobolSyntaxError
from changeproof.adapters.java import JavaAdapter, JavaSyntaxError
from changeproof.change.git import Commit, FileDiff, Ident, checkout_tree, commits_in, file_diffs, origin_url, read_commit
from changeproof.change.message import Trailer, person, tickets, trailers
from changeproof.config import Config
from changeproof.graph.jcl import jcl_module
from changeproof.provenance import Provenance

PROGRAM_SUFFIXES = frozenset({".cbl", ".cob", ".cobol"})  # RENAME: COBOL PROGRAM FILE EXTENSIONS, LOWERCASE
COPYBOOK_SUFFIXES = frozenset({".cpy", ".copy"})  # RENAME: COPYBOOK FILE EXTENSIONS, LOWERCASE
JCL_SUFFIXES = frozenset({".jcl", ".prc", ".proc"})  # RENAME: JCL AND PROC FILE EXTENSIONS, LOWERCASE
JAVA_SUFFIXES = frozenset({".java"})  # RENAME: JAVA SOURCE FILE EXTENSIONS, LOWERCASE
ROLE_TRAILERS = {  # RENAME: TRAILER THAT NAMES EACH ROLE; THE IMPLEMENTER IS ALWAYS THE COMMIT AUTHOR
    "requester": "requested-by", "approver": "approved-by", "reviewer": "reviewed-by",
}
CHANGE_TYPE_TRAILER = "change-type"  # RENAME: TRAILER HOLDING THE CHANGE TYPE (STANDARD, NORMAL OR EMERGENCY)
EMERGENCY_TYPES = frozenset({"emergency", "expedited"})  # RENAME: CHANGE TYPES THAT COUNT AS EMERGENCY
CI_COMMIT_VARIABLES = ("GITHUB_SHA", "CI_COMMIT_SHA", "GIT_COMMIT", "BUILD_SOURCEVERSION")
CI_VARIABLES = (  # RENAME: CI ENVIRONMENT VARIABLES COPIED WHEN THE RUN IS BUILDING THIS COMMIT
    "GITHUB_SERVER_URL", "GITHUB_REPOSITORY", "GITHUB_WORKFLOW", "GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT",
    "CI_PROJECT_PATH", "CI_PIPELINE_ID", "CI_JOB_ID", "JOB_NAME", "BUILD_NUMBER", "BUILD_URL",
    "BUILD_REPOSITORY_NAME", "BUILD_BUILDID",
)


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


class Person(Model):
    name: str
    email: str | None
    provenance: Provenance


class Who(Model):
    implementer: Person  # the commit author
    committer: Person
    requester: Person | None
    approvers: list[Person]
    reviewers: list[Person]
    independent: bool | None  # no approver is the implementer; None when no approver is recorded


class Moment(Model):
    at: str
    provenance: Provenance


class When(Model):
    authored: Moment
    committed: Moment


class Where(Model):
    repository: str
    system: str | None
    commit: str
    parents: list[str]
    files: list[str]
    components: list[str]
    ci: dict[str, str]  # empty unless the CI run analyzing the commit is building that same commit


class What(Model):
    entities: list[EntityChange]
    analyzed: list[str]  # changed files and the programs that copy a changed copybook
    not_analyzed: dict[str, str]  # path to the reason
    problems: dict[str, str]  # path to the error that stopped its analysis


class FileChange(Model):
    path: str
    previous_path: str | None
    status: str
    binary: bool
    insertions: int
    deletions: int
    hunks: list[tuple[Provenance | None, Provenance | None]]  # (before, after) line ranges


class How(Model):
    files: list[FileChange]
    insertions: int
    deletions: int


class Ticket(Model):
    id: str
    system: str
    type: str
    found_in: str
    provenance: Provenance


class TrailerLine(Model):
    key: str
    value: str
    provenance: Provenance


class Why(Model):
    subject: str
    provenance: Provenance
    tickets: list[Ticket]
    change_request: str | None  # first ServiceNow change number named, if any
    change_type: str | None
    emergency: bool | None  # None when the change type is not recorded
    trailers: list[TrailerLine]


class ChangeRecord(Model):
    who: Who
    when: When
    where: Where
    what: What
    how: How
    why: Why

    # PURPOSE: NAMES EACH WHO/WHAT/WHEN/WHERE/HOW PART THAT IS INCOMPLETE (THE WEEK 4 EXIT CHECK)
    def gaps(self) -> list[str]:
        found = []
        if not (self.who.implementer.name and self.who.implementer.email):
            found.append("who: implementer has no name or email")
        if not (self.when.authored.at and self.when.committed.at):
            found.append("when: missing a time")
        if not (self.where.repository and self.where.commit and self.where.files):
            found.append("where: repository, commit or files missing")
        accounted = set(self.what.analyzed) | set(self.what.not_analyzed)
        if self.what.problems or not set(self.where.files) <= accounted:
            found.append("what: a changed file was not accounted for")
        if any(not f.binary and (f.insertions or f.deletions) and not f.hunks for f in self.how.files):
            found.append("how: a text change has no hunks")
        return found

    # PURPOSE: CHANGE-CONTROL FACTS THE REPOSITORY DOES NOT RECORD, LISTED FOR THE REVIEWER
    def open_items(self) -> list[str]:
        found = []
        if self.who.requester is None:
            found.append("no requester recorded")
        if not self.who.approvers:
            found.append("no approver recorded")
        elif not self.who.independent:
            found.append("an approver is also the implementer")
        if self.why.change_request is None:
            found.append("no change request number")
        if self.why.change_type is None:
            found.append("change type not recorded")
        return found


# PURPOSE: A PERSON FROM A COMMIT IDENT
def from_ident(ident: Ident) -> Person:
    return Person(name=ident.name, email=ident.email, provenance=ident.provenance)


# PURPOSE: PEOPLE NAMED IN THE TRAILERS FOR ONE ROLE, IN ORDER
def people(found: list[Trailer], key: str) -> list[Person]:
    return [Person(name=name, email=email, provenance=t.provenance)
            for t in found if t.key.lower() == key for name, email in [person(t.value)]]


# PURPOSE: TRUE WHEN THE TWO PEOPLE ARE THE SAME, BY EMAIL WHEN BOTH HAVE ONE, ELSE BY NAME
def same_person(a: Person, b: Person) -> bool:
    if a.email and b.email:
        return a.email.lower() == b.email.lower()
    return a.name.casefold() == b.name.casefold()


# PURPOSE: BUILDS THE WHO PART: IMPLEMENTER FROM THE AUTHOR, OTHER ROLES FROM TRAILERS
def who_of(commit: Commit, found: list[Trailer]) -> Who:
    implementer = from_ident(commit.author)
    requesters = people(found, ROLE_TRAILERS["requester"])
    approvers = people(found, ROLE_TRAILERS["approver"])
    independent = not any(same_person(a, implementer) for a in approvers) if approvers else None
    return Who(implementer=implementer, committer=from_ident(commit.committer),
               requester=requesters[0] if requesters else None, approvers=approvers,
               reviewers=people(found, ROLE_TRAILERS["reviewer"]), independent=independent)


# PURPOSE: BUILDS THE WHY PART FROM THE SUBJECT, TICKET IDS AND CHANGE-TYPE TRAILER
def why_of(commit: Commit, found: list[Trailer]) -> Why:
    refs = [Ticket(**vars(t)) for t in tickets(commit.message, found)]
    change_type = next((t.value.strip().lower() for t in found if t.key.lower() == CHANGE_TYPE_TRAILER), None)
    subject, where = commit.message[0] if commit.message else ("", commit.committer.provenance)
    return Why(subject=subject, provenance=where, tickets=refs,
               change_request=next((t.id for t in refs if t.type == "change"), None), change_type=change_type,
               emergency=None if change_type is None else change_type in EMERGENCY_TYPES,
               trailers=[TrailerLine(key=t.key, value=t.value, provenance=t.provenance) for t in found])


# PURPOSE: COMPONENT IDS WHOSE PATH HOLDS ANY OF THE FILES, BY LONGEST MATCHING PREFIX
def components_of(files: list[str], config: Config | None) -> list[str]:
    if config is None:
        return []
    by_path = sorted(((c.path.rstrip("/") + "/", c.id) for c in config.components), key=lambda p: -len(p[0]))
    return sorted({next(cid for prefix, cid in by_path if f.startswith(prefix))
                   for f in files if any(f.startswith(prefix) for prefix, _ in by_path)})


# PURPOSE: CI RUN DETAILS, ONLY WHEN THE RUN'S OWN COMMIT VARIABLE NAMES THIS COMMIT
def ci_of(sha: str, environ: Mapping[str, str]) -> dict[str, str]:
    if not any(environ.get(name) == sha for name in CI_COMMIT_VARIABLES):
        return {}
    return {name: environ[name] for name in CI_VARIABLES if environ.get(name)}


# PURPOSE: PROGRAMS IN A TREE WHOSE SOURCE COPIES OR INCLUDES ANY OF THE NAMED COPYBOOKS
def programs_copying(tree: Path, names: set[str]) -> set[str]:
    if not names:
        return set()
    pattern = re.compile(rf"\b(?:COPY|INCLUDE)\s+['\"]?({'|'.join(map(re.escape, sorted(names)))})\b", re.IGNORECASE)
    return {p.relative_to(tree).as_posix() for p in tree.rglob("*")
            if p.suffix.lower() in PROGRAM_SUFFIXES and pattern.search(p.read_text(encoding="latin-1"))}


# PURPOSE: PARSES ONE FILE ON ONE SIDE OF THE CHANGE, OR RETURNS NONE WHEN IT DOES NOT EXIST THERE
def module_at(tree: Path | None, path: str, copybook_dirs: list[str]) -> IRModule | None:
    if tree is None or not (tree / path).is_file():
        return None
    if PurePosixPath(path).suffix.lower() in JCL_SUFFIXES:
        return jcl_module(tree / path, tree)
    if PurePosixPath(path).suffix.lower() in JAVA_SUFFIXES:
        return JavaAdapter().parse(tree / path, tree)
    return CobolAdapter(copybook_dirs).parse(tree / path, tree)


# PURPOSE: BUILDS THE WHAT PART BY PARSING EACH AFFECTED FILE IN TWO TREES ALREADY ON DISK
def what_in(before: Path | None, after: Path, diffs: list[FileDiff], copybook_dirs: list[str]) -> What:
    pairs = {(d.previous_path or d.path, d.path) for d in diffs}  # RENAME: (PATH BEFORE, PATH AFTER) PER FILE
    paths = {p for pair in pairs for p in pair}
    copybooks = {p for p in paths if PurePosixPath(p).suffix.lower() in COPYBOOK_SUFFIXES
                 or any(p.startswith(d.rstrip("/") + "/") for d in copybook_dirs)}
    parsable = PROGRAM_SUFFIXES | JCL_SUFFIXES | JAVA_SUFFIXES
    pairs = {(a, b) for a, b in pairs if b not in copybooks and PurePosixPath(b).suffix.lower() in parsable}
    analyzed = copybooks | {p for pair in pairs for p in pair}
    not_analyzed = {p: "no adapter for this file type" for p in sorted(paths - analyzed)}
    if not pairs and not copybooks:
        return What(entities=[], analyzed=[], not_analyzed=not_analyzed, problems={})
    names = {PurePosixPath(p).stem.upper() for p in copybooks}
    copying = programs_copying(after, names) | (programs_copying(before, names) if before else set())
    pairs |= {(p, p) for p in copying if not any(p in pair for pair in pairs)}
    entities, problems = [], {}
    for old_path, new_path in sorted(pairs):
        try:
            old, new = module_at(before, old_path, copybook_dirs), module_at(after, new_path, copybook_dirs)
        except (CobolSyntaxError, JavaSyntaxError) as exc:
            problems[new_path] = "; ".join(f"{where}: {msg}" for where, msg in exc.errors[:3])
            continue
        entities += diff_by_id(old, new)
    return What(entities=entities, analyzed=sorted(analyzed | copying), not_analyzed=not_analyzed,
                problems=problems)


# PURPOSE: BUILDS THE WHAT PART FOR ONE COMMIT, CHECKING OUT EACH SIDE ONLY WHEN SOMETHING NEEDS PARSING
def what_of(root: Path, commit: Commit, diffs: list[FileDiff], copybook_dirs: list[str]) -> What:
    with tempfile.TemporaryDirectory() as scratch:
        after = checkout_tree(root, commit.sha, Path(scratch) / "after")
        before = checkout_tree(root, commit.parents[0], Path(scratch) / "before") if commit.parents else None
        return what_in(before, after, diffs, copybook_dirs)


# PURPOSE: BUILDS THE FULL RECORD FOR ONE COMMIT
def change_record(root: Path, sha: str, copybook_dirs: list[str] = (), config: Config | None = None,
                  environ: Mapping[str, str] = os.environ) -> ChangeRecord:
    commit = read_commit(root, sha)
    found = trailers(commit.message)
    diffs = file_diffs(root, commit)
    files = sorted({d.path for d in diffs} | {d.previous_path for d in diffs if d.previous_path})
    how = How(
        files=[FileChange(path=d.path, previous_path=d.previous_path, status=d.status, binary=d.insertions is None,
                          insertions=d.insertions or 0, deletions=d.deletions or 0, hunks=d.hunks) for d in diffs],
        insertions=sum(d.insertions or 0 for d in diffs), deletions=sum(d.deletions or 0 for d in diffs),
    )
    return ChangeRecord(
        who=who_of(commit, found),
        when=When(authored=Moment(at=commit.author.at, provenance=commit.author.provenance),
                  committed=Moment(at=commit.committer.at, provenance=commit.committer.provenance)),
        where=Where(repository=origin_url(root) or Path(root).resolve().name,
                    system=config.system.name if config else None, commit=sha, parents=commit.parents,
                    files=files, components=components_of(files, config), ci=ci_of(sha, environ)),
        what=what_of(root, commit, diffs, list(copybook_dirs)),
        how=how,
        why=why_of(commit, found),
    )


# PURPOSE: RECORDS FOR EVERY COMMIT IN A RANGE, OLDEST FIRST
def change_records(root: Path, revisions: str, copybook_dirs: list[str] = (), config: Config | None = None,
                   environ: Mapping[str, str] = os.environ) -> list[ChangeRecord]:
    return [change_record(root, sha, copybook_dirs, config, environ) for sha in commits_in(root, revisions)]
