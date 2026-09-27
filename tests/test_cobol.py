from legacylens.parsers.cobol import parse_cobol


def test_cics_program_structure(read):
    program = parse_cobol(read("cobol/ACCTINQ.cbl"))
    assert program.program_id == "ACCTINQ"
    assert program.program_type == "cics-online"
    assert program.copybooks == ["ACCTMAP", "CUSTREC"]

    paragraphs = {p.name: p for p in program.paragraphs}
    assert paragraphs["0000-MAIN"].performs == ["1000-SEND-EMPTY-MAP", "2000-PROCESS-INPUT"]
    assert "4000-CHECK-STATUS" in paragraphs["3000-READ-CUSTOMER"].performs


def test_cics_commands_and_options(read):
    program = parse_cobol(read("cobol/ACCTINQ.cbl"))
    reads = [c for c in program.cics_commands if c.command == "READ"]
    assert reads[0].options["FILE"] == "CUSTMAST"
    assert reads[0].paragraph == "3000-READ-CUSTOMER"
    links = [c for c in program.cics_commands if c.command == "LINK"]
    assert links[0].options["PROGRAM"] == "ERRLOG"
    maps = [c for c in program.cics_commands if c.command == "SEND MAP"]
    assert {c.options["MAP"] for c in maps} == {"ACCTMAP"}


def test_batch_program(read):
    program = parse_cobol(read("cobol/INTCALC.cbl"))
    assert program.program_type == "batch"
    assert [f.ddname for f in program.files] == ["CUSTIN", "CUSTOUT", "EXCPRPT"]
    assert program.static_calls == ["AUDITLOG"]
    assert all(keyword not in p.performs for p in program.paragraphs for keyword in ("UNTIL", "VARYING"))
