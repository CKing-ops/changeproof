import shutil
from pathlib import Path

import pytest

from changeproof.adapters import Adapter, AdapterRegistry, ChangeKind
from changeproof.adapters.cobol import CobolAdapter
from changeproof.adapters.cobol.parse import CobolSyntaxError

ROOT = Path(__file__).resolve().parent / "fixtures" / "cobol"


@pytest.fixture(scope="module")
def adapter() -> CobolAdapter:
    return CobolAdapter(copybook_dirs=["copy"])


@pytest.fixture(scope="module")
def module(adapter):
    return adapter.parse(ROOT / "src" / "PAYCALC.cbl", ROOT)


@pytest.fixture(scope="module")
def by_id(module):
    return {e.id: e for e in module.entities}


def at(entity) -> str:
    return str(entity.provenance)


def test_adapter_fits_the_interface_and_registers(adapter):
    assert isinstance(adapter, Adapter)
    registry = AdapterRegistry()
    registry.register(adapter)
    assert registry.get("cobol") is adapter


def test_module_header(module):
    assert (module.path, module.language) == ("src/PAYCALC.cbl", "cobol")


def test_entity_ids_are_unique(module):
    ids = [e.id for e in module.entities]
    assert len(ids) == len(set(ids))


def test_program_section_and_paragraphs(by_id):
    assert at(by_id["program:PAYCALC"]) == "src/PAYCALC.cbl:1-39"
    assert at(by_id["paragraph:PAYCALC.MAIN-PARA"]) == "src/PAYCALC.cbl:24-29"
    assert at(by_id["section:PAYCALC.CALC-SECTION"]) == "src/PAYCALC.cbl:30-39"
    para = by_id["paragraph:PAYCALC.CALC-SECTION.CALC-PARA"]
    assert at(para) == "src/PAYCALC.cbl:31-39"
    assert para.attributes["section"] == "section:PAYCALC.CALC-SECTION"


def test_paragraph_text_includes_replaced_copybook_code(by_id):
    text = by_id["paragraph:PAYCALC.CALC-SECTION.CALC-PARA"].attributes["text"]
    assert "COMPUTE WS-TOTAL = WS-TOTAL * WS-RATE ( 1 )" in text


def test_data_items_from_a_copybook_point_at_the_copybook(by_id):
    total = by_id["data:PAYCALC.WS-TOTALS.WS-TOTAL"]
    assert at(total) == "copy/PAYWS.cpy:3"
    assert total.attributes | {"text": None} == {
        "level": "05", "picture": "S9(7)V99", "parent": "data:PAYCALC.WS-TOTALS",
        "section": "working-storage", "text": None,
    }
    assert at(by_id["condition:PAYCALC.WS-TOTALS.WS-COUNT.WS-NO-ROWS"]) == "copy/PAYWS.cpy:5"


def test_data_items_in_the_program(by_id):
    assert at(by_id["data:PAYCALC.WS-RATE-TABLE.WS-RATE"]) == "src/PAYCALC.cbl:16"
    assert at(by_id["data:PAYCALC.WS-NOTE"]) == "src/PAYCALC.cbl:19-20"
    assert by_id["data:PAYCALC.PAY-REC"].attributes["section"] == "file"
    assert by_id["data:PAYCALC.LK-EMP-ID"].attributes["section"] == "linkage"


def test_file_and_copy_statements(by_id):
    pay_file = by_id["file:PAYCALC.PAY-FILE"]
    assert (at(pay_file), pay_file.attributes["assign"]) == ("src/PAYCALC.cbl:8", "PAYIN")
    rule = by_id["copybook:PAYCALC.PAYRULE#1"]
    assert at(rule) == "src/PAYCALC.cbl:32-33"
    assert rule.attributes == {"resolved": "copy/PAYRULE.cpy", "problem": None,
                               "replacing": [[":PFX:", "WS"], ["BONUS-RATE", "WS-RATE (1)"]]}


def test_static_call(by_id):
    call = by_id["call:PAYCALC.MAIN-PARA.PAYAUDIT#1"]
    assert at(call) == "src/PAYCALC.cbl:26"
    assert call.attributes == {"target": "PAYAUDIT", "dynamic": False, "paragraph": "paragraph:PAYCALC.MAIN-PARA"}


def test_crypto_calls_are_tagged(by_id):
    dynamic = by_id["crypto-call:PAYCALC.MAIN-PARA.CSNBOWH#1"]
    assert at(dynamic) == "src/PAYCALC.cbl:27"
    assert dynamic.attributes == {
        "service": "CSNBOWH", "category": "hash", "via": "call", "dynamic": True,
        "target_from": "data:PAYCALC.WS-HASH-SVC", "paragraph": "paragraph:PAYCALC.MAIN-PARA",
    }
    sign = by_id["crypto-call:PAYCALC.CALC-SECTION.CALC-PARA.CSNDDSG#1"]
    assert (at(sign), sign.attributes["category"]) == ("src/PAYCALC.cbl:39", "signature-generate")
    sql = by_id["crypto-call:PAYCALC.CALC-SECTION.CALC-PARA.HASH_SHA256#1"]
    assert (at(sql), sql.attributes["via"], sql.attributes["category"]) == ("src/PAYCALC.cbl:34-37", "sql", "hash")


def test_exec_blocks_become_entities(by_id):
    sql = by_id["exec-sql:PAYCALC.CALC-SECTION.CALC-PARA#1"]
    assert at(sql) == "src/PAYCALC.cbl:34-37"
    assert sql.attributes["text"].startswith("SELECT HASH_SHA256(EMP_NAME)")
    cics = by_id["exec-cics:PAYCALC.CALC-SECTION.CALC-PARA#1"]
    assert (at(cics), cics.attributes["command"], cics.attributes["program"]) == ("src/PAYCALC.cbl:38", "LINK", "PAYLOG")


def test_every_named_fact_is_on_its_provenance_line(module):
    for entity in module.entities:
        lines = (ROOT / entity.provenance.file).read_text(encoding="latin-1").splitlines()
        span = lines[entity.provenance.line - 1:(entity.provenance.end_line or entity.provenance.line)]
        token = entity.name.split("#")[0]
        assert any(token.upper() in ln.upper() for ln in span), (entity.id, str(entity.provenance), token)


def test_missing_copybook_is_an_entity_with_a_problem(adapter):
    module = adapter.parse(ROOT / "src" / "NOCOPY.cbl", ROOT)
    (copy,) = [e for e in module.entities if e.kind == "copybook"]
    assert (copy.name, copy.attributes["problem"]) == ("NOSUCHBOOK", "copybook not found")


def test_syntax_errors_point_at_the_source_line(adapter, tmp_path):
    bad = tmp_path / "src"
    bad.mkdir()
    (bad / "BAD.cbl").write_text(
        "       IDENTIFICATION DIVISION.\n       PROGRAM-ID. BAD.\n       PROCEDURE DIVISION.\n"
        "       MAIN-PARA.\n           MOVE TO TO.\n"
    )
    with pytest.raises(CobolSyntaxError) as err:
        adapter.parse(bad / "BAD.cbl", tmp_path)
    assert str(err.value.errors[0][0]) == "src/BAD.cbl:5"


def test_diff_ignores_moved_lines_and_catches_a_picture_change(adapter, module, tmp_path):
    shutil.copytree(ROOT, tmp_path, dirs_exist_ok=True)
    program = tmp_path / "src" / "PAYCALC.cbl"
    lines = program.read_text().splitlines(keepends=True)
    program.write_text("".join(lines[:4] + ["      *    AN ADDED COMMENT\n", "\n"] + lines[4:]))
    moved = adapter.parse(program, tmp_path)
    assert adapter.diff(module, moved) == []

    copybook = tmp_path / "copy" / "PAYWS.cpy"
    copybook.write_text(copybook.read_text().replace("PIC 9(5).", "PIC 9(7)."))
    changed = adapter.diff(module, adapter.parse(program, tmp_path))
    assert [(c.change, c.entity.id) for c in changed] == [(ChangeKind.MODIFIED, "data:PAYCALC.WS-TOTALS.WS-COUNT")]
    assert str(changed[0].entity.provenance) == "copy/PAYWS.cpy:4"


def test_run_is_planned_for_week_8(adapter, module):
    with pytest.raises(NotImplementedError, match="Week 8"):
        adapter.run(module, {})


def test_perform_is_a_fact_with_its_statement_line(by_id):
    perform = by_id["perform:PAYCALC.MAIN-PARA.CALC-PARA#1"]
    assert at(perform) == "src/PAYCALC.cbl:25"
    assert perform.attributes == {"target": "CALC-PARA", "paragraph": "paragraph:PAYCALC.MAIN-PARA"}


def test_perform_thru_and_go_to(adapter):
    root = Path(__file__).resolve().parent / "fixtures" / "graph"
    module = CobolAdapter(copybook_dirs=["copy"]).parse(root / "src" / "BATCH1.cbl", root)
    facts = {e.id: e for e in module.entities}
    thru = facts["perform:BATCH1.MAIN-PARA.OPEN-PARA#1"]
    assert (at(thru), thru.attributes["thru"]) == ("src/BATCH1.cbl:20", "OPEN-EXIT")
    assert at(facts["perform:BATCH1.MAIN-PARA.READ-PARA#1"]) == "src/BATCH1.cbl:21"
    go = facts["goto:BATCH1.MAIN-PARA.END-PARA#1"]
    assert (at(go), go.attributes["target"]) == ("src/BATCH1.cbl:25", "END-PARA")
