from pathlib import Path

from changeproof.adapters.base import diff_by_id
from changeproof.graph.jcl import jcl_module, parse_jcl

ROOT = Path(__file__).resolve().parent / "fixtures" / "graph"


def test_job_steps_and_dd_statements():
    (job,) = parse_jcl(ROOT / "jcl" / "RUNBATCH.jcl", ROOT)
    assert (job.name, str(job.provenance)) == ("RUNBATCH", "jcl/RUNBATCH.jcl:1-2")
    assert [(s.name, s.program, s.proc, str(s.provenance)) for s in job.steps] == [
        ("STEP01", "BATCH1", None, "jcl/RUNBATCH.jcl:4"),
        ("STEP02", "IEFBR14", None, "jcl/RUNBATCH.jcl:12"),
        ("STEP03", None, "NIGHTLY", "jcl/RUNBATCH.jcl:13"),
    ]


def test_dd_statements_keep_dataset_disposition_and_line():
    (job,) = parse_jcl(ROOT / "jcl" / "RUNBATCH.jcl", ROOT)
    dds = {d.name: d for d in job.steps[0].dds}
    assert (dds["ACCTIN"].dataset, dds["ACCTIN"].disp, str(dds["ACCTIN"].provenance)) == (
        "TEST.ACCT.DATA", "SHR", "jcl/RUNBATCH.jcl:5-6")
    assert (dds["RPTOUT"].dataset, dds["RPTOUT"].disp) == ("TEST.RPT.OUT", "(NEW,CATLG)")
    assert dds["SYSOUT"].dataset is None
    assert "SYSIN" in dds and dds["SYSIN"].dataset is None


def test_instream_data_is_not_parsed_as_statements():
    (job,) = parse_jcl(ROOT / "jcl" / "RUNBATCH.jcl", ROOT)
    assert all("CONTROL" not in d.name for s in job.steps for d in s.dds)


def test_programs_run_through_tso_batch_and_ims_regions():
    (job,) = parse_jcl(ROOT / "jcl" / "INDIRECT.jcl", ROOT)
    assert [(s.name, s.program, [(name, str(where)) for name, where in s.runs]) for s in job.steps] == [
        ("DB2STEP", "IKJEFT01", [("BATCH1", "jcl/INDIRECT.jcl:7")]),
        ("IMSSTEP", "DFSRRC00", [("SUBPGM", "jcl/INDIRECT.jcl:10-11")]),
        ("NEXT", "IEFBR14", []),
    ]


CASH = Path(__file__).resolve().parent.parent / "corpus" / "ibm-cash-account"


def test_instream_ddl_names_the_tables_it_defines_with_their_lines():
    (job,) = parse_jcl(CASH / "DB2-DDL" / "DB2DDL.jcl", CASH)
    sysin = {s.name: next(d for d in s.dds if d.name == "SYSIN") for s in job.steps}
    assert [(kind, name, str(where)) for kind, name, _, where in sysin["CRTABS"].defines] == [
        ("table", "STOCKTRD.CASHACCOUNTY", "DB2-DDL/DB2DDL.jcl:46-52"),
        ("table", "STOCKTRD.FRANKFURT1", "DB2-DDL/DB2DDL.jcl:54-62")]
    assert "NUMERIC(9,2)" in sysin["CRTABS"].defines[0][2]
    assert sysin["CREATE"].defines == () and "CREATE STOGROUP SGSTAPP" in sysin["CREATE"].data


def test_an_idcams_define_cluster_names_the_dataset_it_defines():
    (job,) = parse_jcl(CASH / "VSAM" / "DEFKSDS.jcl", CASH)
    (sysin,) = [d for d in job.steps[0].dds if d.name == "SYSIN"]
    ((kind, name, text, where),) = sysin.defines
    assert (kind, name, str(where)) == ("dataset", "SYSD.STOCK.HISTORY", "VSAM/DEFKSDS.jcl:9-16")
    assert "KEYS(29 0)" in text


def test_an_instream_edit_changes_the_dd_and_the_table_definition_entities(tmp_path):
    text = (CASH / "DB2-DDL" / "DB2DDL.jcl").read_text(encoding="latin-1")
    for side, body in (("old", text), ("new", text.replace("balance      NUMERIC(9,2)", "balance      NUMERIC(11,2)"))):
        (tmp_path / side).mkdir()
        (tmp_path / side / "DB2DDL.jcl").write_text(body, encoding="latin-1")
    old, new = (jcl_module(tmp_path / side / "DB2DDL.jcl", tmp_path / side) for side in ("old", "new"))
    changed = sorted((c.change.value, c.entity.id) for c in diff_by_id(old, new))
    assert changed == [("modified", "jcl-dd:DB2DDL.CRTABS.SYSIN"),
                       ("modified", "jcl-define:DB2DDL.CRTABS.SYSIN.STOCKTRD.CASHACCOUNTY")]
