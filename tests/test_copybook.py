from legacylens.parsers.copybook import expand_picture, flatten, numeric_storage, parse_copybook


def test_expand_picture():
    assert expand_picture("S9(7)V99") == "S9999999V99"
    assert expand_picture("X(3)") == "XXX"


def test_packed_and_binary_storage():
    assert numeric_storage(9, "COMP-3") == 5
    assert numeric_storage(4, "COMP") == 2
    assert numeric_storage(8, "COMP") == 4
    assert numeric_storage(8, "DISPLAY") == 8


def test_customer_record_layout(read):
    copybook = parse_copybook(read("copybooks/CUSTREC.cpy"), "CUSTREC")
    rows = {r["path"].split(".")[-1]: r for r in flatten(copybook.fields)}

    assert copybook.record_length == 181
    assert rows["CUST-CREDIT-LIMIT"]["usage"] == "COMP-3"
    assert rows["CUST-CREDIT-LIMIT"]["length"] == 5
    assert rows["CUST-PHONE"]["occurs"] == 3
    assert rows["CUST-PHONE"]["length"] == 36
    # REDEFINES overlays the same storage as the field it names
    assert rows["CUST-ADDRESS-ALT"]["offset"] == rows["CUST-ADDRESS"]["offset"] == 110
    assert rows["CUST-LAST-TXN-AMT"]["offset"] == 167


def test_level_88_conditions(read):
    copybook = parse_copybook(read("copybooks/CUSTREC.cpy"), "CUSTREC")
    status = next(f for f in copybook.fields[0].children if f.name == "CUST-STATUS")
    assert {c.name: c.values for c in status.conditions} == {"CUST-ACTIVE": ["A"], "CUST-CLOSED": ["C"]}
