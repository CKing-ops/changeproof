import importlib.util
from pathlib import Path

import pytest

from changeproof.change import change_record
from changeproof.change.message import person, tickets, trailers
from changeproof.change.record import ci_of
from changeproof.config import load_config
from changeproof.provenance import Provenance

SEED = Path(__file__).resolve().parent / "fixtures" / "change" / "seed.py"


def message(*lines):
    return [(text, Provenance(file="git-commit/abc", line=n)) for n, text in enumerate(lines, 6)]


@pytest.fixture(scope="module")
def records(tmp_path_factory):
    spec = importlib.util.spec_from_file_location("seed", SEED)
    seed = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(seed)
    root = tmp_path_factory.mktemp("sepa")
    shas = seed.seed(root)
    config = load_config(root / "changeproof.yaml")
    return [change_record(root, sha, copybook_dirs=["copy"], config=config, environ={}) for sha in shas]


def ids(record, change):
    return sorted(c.entity.id for c in record.what.entities if c.change == change)


def test_trailers_are_the_last_paragraph_only_when_every_line_is_key_value():
    msg = message("Fix fee", "", "Body: not a trailer block", "because of this line", "",
                  "Change-Request: CHG0030001", "Approved-by: Marc Dubois <marc@bank.example>")
    assert [(t.key, t.value, t.provenance.line) for t in trailers(msg)] == [
        ("Change-Request", "CHG0030001", 11), ("Approved-by", "Marc Dubois <marc@bank.example>", 12)]
    assert trailers(message("Fix fee", "", "Just a closing sentence: with a colon", "and more")) == []


def test_ticket_ids_are_copied_from_the_message_never_guessed():
    msg = message("PAY-7: Fix fee per ISO-27001 and SHA-256", "", "See [OPS-12] and INC0045678, not AB-1 here.", "",
                  "Refs: CHG0030001, PAY-9", "Reviewed-by: Rui Costa <rui@bank.example>")
    found = tickets(msg, trailers(msg))
    assert [(t.id, t.system, t.type, t.found_in, t.provenance.line) for t in found] == [
        ("CHG0030001", "servicenow", "change", "trailer", 10),
        ("PAY-9", "jira", "issue", "trailer", 10),
        ("PAY-7", "jira", "issue", "subject", 6),
        ("INC0045678", "servicenow", "incident", "body", 8),
        ("OPS-12", "jira", "issue", "body", 8),
    ]


def test_person_splits_name_and_email():
    assert person("Marc Dubois <marc@bank.example>") == ("Marc Dubois", "marc@bank.example")
    assert person("Change Board") == ("Change Board", None)


def test_ci_details_are_kept_only_for_a_run_building_the_same_commit():
    env = {"GITHUB_SHA": "abc", "GITHUB_RUN_ID": "42", "GITHUB_REPOSITORY": "bank/sepa", "HOME": "/root"}
    assert ci_of("abc", env) == {"GITHUB_REPOSITORY": "bank/sepa", "GITHUB_RUN_ID": "42"}
    assert ci_of("def", env) == {}


def test_exit_check_ten_seeded_commits_give_complete_records(records):
    assert len(records) == 10
    assert [(r.why.subject, r.gaps()) for r in records if r.gaps()] == []


def test_who_keeps_requester_implementer_and_approver_apart(records):
    first = records[0].who
    assert (first.requester.name, first.implementer.name, [a.name for a in first.approvers], first.independent) == \
        ("Lena Weber", "Ana Novak", ["Marc Dubois"], True)
    assert str(first.implementer.provenance).startswith("git-commit/")
    assert (records[2].who.implementer.name, records[2].who.committer.name) == ("Tomas Horvat", "Release Bot")


def test_an_approver_who_implemented_the_change_is_flagged(records):
    emergency = records[8]
    assert (emergency.why.change_type, emergency.why.emergency, emergency.who.independent) == ("emergency", True, False)
    assert "an approver is also the implementer" in emergency.open_items()


def test_missing_why_is_recorded_as_missing(records):
    last = records[9]
    assert (last.why.tickets, last.why.change_request, last.why.emergency, last.who.approvers) == ([], None, None, [])
    assert last.open_items() == ["no requester recorded", "no approver recorded", "no change request number",
                                 "change type not recorded"]


def test_when_keeps_the_committers_own_offset(records):
    assert (records[0].when.authored.at, records[0].when.committed.at) == \
        ("2026-09-01T09:30:00+02:00", "2026-09-01T09:30:00+02:00")


def test_where_names_files_and_components(records):
    assert records[1].where.files == ["src/FLOWS.cbl"]
    assert records[1].where.components == ["batch-core"]
    assert records[4].where.files == ["src/SUBPGM.cbl", "src/online/SUBPGM.cbl"]
    assert records[0].where.system == "test-payments"


def test_what_is_field_level_for_a_statement_edit(records):
    assert ids(records[1], "modified") == ["flow:FLOWS.MAIN-PARA.WS-FEE#1", "paragraph:FLOWS.MAIN-PARA"]
    assert records[1].why.tickets[0].id == "PAY-101"


def test_what_follows_a_copybook_into_the_programs_that_copy_it(records):
    assert ids(records[2], "added") == ["data:BATCH1.WS-LIMIT"]
    added = records[2].what.entities[0].entity
    assert str(added.provenance) == "copy/ACCTWS.cpy:5"
    assert "src/BATCH1.cbl" in records[2].what.analyzed


def test_what_for_added_then_removed_paragraphs(records):
    assert ids(records[3], "added") == ["flow:BATCH1.AUDIT-PARA.WS-COUNT#1", "paragraph:BATCH1.AUDIT-PARA",
                                        "perform:BATCH1.READ-PARA.AUDIT-PARA#1"]
    assert ids(records[3], "modified") == ["paragraph:BATCH1.READ-PARA"]
    assert ids(records[6], "removed") == ids(records[3], "added")


def test_a_move_or_a_comment_changes_no_entity(records):
    moved, comment = records[4], records[7]
    assert (moved.how.files[0].status, moved.how.files[0].previous_path) == ("R", "src/SUBPGM.cbl")
    assert moved.what.entities == [] and comment.what.entities == []
    assert comment.how.files[0].hunks[0][1] is not None


def test_what_for_a_jcl_change(records):
    [change] = records[5].what.entities
    assert (change.entity.id, change.previous.attributes["dataset"], change.entity.attributes["dataset"]) == \
        ("jcl-dd:RUNBATCH.STEP01.ACCTIN", "TEST.ACCT.DATA", "TEST.ACCT.DATA.V2")


def test_how_gives_hunk_ranges_on_both_sides(records):
    [edit] = records[8].how.files
    [(before, after)] = edit.hunks
    assert (str(before), str(after), edit.insertions, edit.deletions) == \
        ("src/FLOWS.cbl:31", "src/FLOWS.cbl:31-33", 3, 1)


def test_a_crypto_change_and_an_unanalyzed_file(records):
    last = records[9]
    assert ids(last, "added") == ["crypto-call:SUBPGM.MAIN-PARA.CSNBHMG#1"]
    assert ids(last, "removed") == ["crypto-call:SUBPGM.MAIN-PARA.CSNBOWH#1"]
    assert last.what.not_analyzed == {"README.md": "no adapter for this file type"}
