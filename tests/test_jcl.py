from pathlib import Path

from changeproof.graph.jcl import parse_jcl

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
