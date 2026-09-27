from legacylens.parsers import parse_bms, parse_jcl, parse_mfs


def test_bms_map(read):
    (screen,) = parse_bms(read("bms/ACCTSET.bms"))
    assert (screen.mapset, screen.map_name, screen.size) == ("ACCTSET", "ACCTMAP", (24, 80))
    fields = {f.name: f for f in screen.fields if f.name}
    assert fields["CUSTID"].input and fields["CUSTID"].length == 8
    assert not fields["NAME"].input
    assert (fields["MSG"].row, fields["MSG"].column) == (22, 5)
    labels = [f.initial for f in screen.fields if f.initial]
    assert "ACCOUNT INQUIRY" in labels


def test_mfs_format_and_messages(read):
    (fmt,) = parse_mfs(read("mfs/CUSTFMT.mfs"))
    fields = {f.name: f for f in fmt.screen.fields if f.name}
    assert fields["CUSTNO"].input
    assert fields["CNAME"].length == 45
    directions = {m.name: m.direction for m in fmt.messages}
    assert directions == {"CUSTIN": "input", "CUSTOUT": "output"}


def test_jcl_with_proc_expansion(read):
    job = parse_jcl(read("jcl/NIGHTINT.jcl"), {"INTPROC": read("proclib/INTPROC.proc")})
    assert job.job_name == "NIGHTINT"
    assert job.description == "NIGHTLY INTEREST"
    steps = {s.step_name: s for s in job.steps}
    calc = steps["STEP020.CALC"]
    assert calc.program == "INTCALC"
    assert calc.expanded_from_proc == "INTPROC"
    dsns = {d.ddname: d.dsn for d in calc.dd_statements}
    # &ENV..CUST.MASTER with ENV=PROD from the calling EXEC
    assert dsns["CUSTIN"] == "PROD.CUST.MASTER"
    assert steps["STEP030"].condition == "(4,LT)"
    assert any(d.instream for d in steps["STEP030"].dd_statements)
