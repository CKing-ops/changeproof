"""Reads commits from a local git repository through the git command line. Nothing here touches the network."""

import re
import subprocess
import tarfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path

from changeproof.provenance import Provenance

IDENT_RE = re.compile(r"^(author|committer) (.*) <(.*)> (\d+) ([+-])(\d\d)(\d\d)$")
HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")
GIT_OPTIONS = ("-c", "core.quotePath=false", "-c", "diff.noprefix=false")  # RENAME: CONFIG PINNED FOR STABLE OUTPUT


@dataclass(frozen=True)
class Ident:
    name: str
    email: str
    at: str  # ISO 8601 with the committer's own UTC offset
    provenance: Provenance


@dataclass
class Commit:
    sha: str
    parents: list[str]
    author: Ident
    committer: Ident
    message: list[tuple[str, Provenance]]  # RENAME: MESSAGE LINES WITH THEIR LINE IN THE COMMIT OBJECT


@dataclass
class FileDiff:
    status: str  # A, M, D, R, C or T, as git diff-tree reports it
    path: str
    previous_path: str | None
    insertions: int | None  # None for a binary file
    deletions: int | None
    hunks: list[tuple[Provenance | None, Provenance | None]] = field(default_factory=list)


# PURPOSE: RUNS ONE GIT COMMAND IN THE REPOSITORY AND RETURNS ITS RAW OUTPUT
def git(root: Path, *args: str) -> bytes:
    return subprocess.run(["git", *GIT_OPTIONS, "-C", str(root), *args], check=True, capture_output=True).stdout


# PURPOSE: COMMITS IN A RANGE, OLDEST FIRST; A SINGLE REVISION MEANS JUST THAT COMMIT
def commits_in(root: Path, revisions: str) -> list[str]:
    if ".." in revisions:
        return git(root, "rev-list", "--reverse", revisions).decode().split()
    return [git(root, "rev-parse", "--verify", f"{revisions}^{{commit}}").decode().strip()]


# PURPOSE: PROVENANCE FOR A LINE OF THE RAW COMMIT OBJECT, AS GIT CAT-FILE COMMIT PRINTS IT
def object_line(sha: str, line: int) -> Provenance:
    return Provenance(file=f"git-commit/{sha}", line=line)


# PURPOSE: TURNS AN AUTHOR OR COMMITTER HEADER INTO AN IDENT WITH ITS LOCAL TIME
def ident(match: re.Match, where: Provenance) -> Ident:
    offset = timedelta(hours=int(match.group(6)), minutes=int(match.group(7)))
    zone = timezone(-offset if match.group(5) == "-" else offset)
    at = datetime.fromtimestamp(int(match.group(4)), zone).isoformat()
    return Ident(name=match.group(2), email=match.group(3), at=at, provenance=where)


# PURPOSE: PARSES THE RAW COMMIT OBJECT, KEEPING THE LINE NUMBER OF EVERY HEADER AND MESSAGE LINE
def read_commit(root: Path, sha: str) -> Commit:
    lines = git(root, "cat-file", "commit", sha).decode("utf-8", errors="replace").split("\n")
    parents, people = [], {}
    body = len(lines)
    for number, line in enumerate(lines, 1):
        if line == "":
            body = number
            break
        if line.startswith("parent "):
            parents.append(line.split()[1])
        elif m := IDENT_RE.match(line):
            people[m.group(1)] = ident(m, object_line(sha, number))
    message = [(text, object_line(sha, number)) for number, text in enumerate(lines[body:], body + 1)]
    while message and not message[-1][0].strip():
        message.pop()
    return Commit(sha=sha, parents=parents, author=people["author"], committer=people["committer"], message=message)


# PURPOSE: PAIRS UP NUL-SEPARATED NAME-STATUS OUTPUT INTO (STATUS, PATH, PREVIOUS PATH) PER CHANGED FILE
def name_status(raw: bytes) -> list[tuple[str, str, str | None]]:
    parts = raw.decode("utf-8").split("\0")
    found, i = [], 0
    while i < len(parts) and parts[i]:
        status = parts[i]
        if status[0] in "RC":
            found.append((status[0], parts[i + 2], parts[i + 1]))
            i += 3
        else:
            found.append((status[0], parts[i + 1], None))
            i += 2
    return found


# PURPOSE: PARSES -U0 HUNK HEADERS INTO (BEFORE, AFTER) LINE RANGES; A SIDE WITH NO LINES IS NONE
def hunks_of(patch: str, before_path: str | None, after_path: str | None) -> list[tuple[Provenance | None, Provenance | None]]:
    found = []
    for line in patch.splitlines():
        if m := HUNK_RE.match(line):
            old_start, old_len = int(m.group(1)), int(m.group(2) or 1)
            new_start, new_len = int(m.group(3)), int(m.group(4) or 1)
            before = Provenance(file=before_path, line=old_start, end_line=old_start + old_len - 1) \
                if old_len and before_path else None
            after = Provenance(file=after_path, line=new_start, end_line=new_start + new_len - 1) \
                if new_len and after_path else None
            found.append((before, after))
    return found


# PURPOSE: FILES A COMMIT CHANGED AGAINST ITS FIRST PARENT, WITH LINE COUNTS AND HUNK RANGES
def file_diffs(root: Path, commit: Commit) -> list[FileDiff]:
    base = ["--root", commit.sha] if not commit.parents else [commit.parents[0], commit.sha]
    statuses = name_status(git(root, "diff-tree", "-r", "-M", "--no-commit-id", "--name-status", "-z", *base))
    counts = {}
    numstat = git(root, "diff-tree", "-r", "-M", "--no-commit-id", "--numstat", "-z", *base).decode("utf-8").split("\0")
    i = 0
    while i < len(numstat) and numstat[i]:
        added, removed, path = numstat[i].split("\t", 2)
        if path == "":
            path, i = numstat[i + 2], i + 3
        else:
            i += 1
        counts[path] = (None, None) if added == "-" else (int(added), int(removed))
    diffs = []
    for status, path, previous in statuses:
        insertions, deletions = counts.get(path, (0, 0))
        before = None if status == "A" else previous or path
        after = None if status == "D" else path
        patch = git(root, "diff-tree", "-p", "-U0", "-M", "--no-color", "--no-ext-diff", "--no-commit-id", *base,
                    "--", *filter(None, {before, after})).decode("utf-8", errors="replace")
        diffs.append(FileDiff(status=status, path=path, previous_path=previous, insertions=insertions,
                              deletions=deletions, hunks=hunks_of(patch, before, after)))
    return diffs


# PURPOSE: WRITES THE TREE OF A COMMIT INTO A FOLDER SO ADAPTERS CAN PARSE IT FROM DISK
def checkout_tree(root: Path, sha: str, target: Path) -> Path:
    with tarfile.open(fileobj=BytesIO(git(root, "archive", "--format=tar", sha))) as archive:
        archive.extractall(target, filter="data")
    return target


# PURPOSE: THE REPOSITORY'S ORIGIN URL FROM LOCAL CONFIG, OR NONE
def origin_url(root: Path) -> str | None:
    result = subprocess.run(["git", "-C", str(root), "config", "--get", "remote.origin.url"], capture_output=True)
    return result.stdout.decode().strip() or None
