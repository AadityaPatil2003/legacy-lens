"""Parse COBOL copybooks (record layouts) into a typed field tree.

Handles level numbers, PIC clauses (X, 9, S, V, repeat counts),
USAGE (DISPLAY, COMP/BINARY, COMP-3/PACKED-DECIMAL), OCCURS, REDEFINES,
level-88 condition names and FILLER, and computes byte lengths and offsets.
"""

from __future__ import annotations

import re

from legacylens.models import ConditionName, Copybook, DataField
from legacylens.parsers.common import cobol_logical_lines, split_statements

_ENTRY = re.compile(r"^(?P<level>\d{1,2})\s+(?P<name>[A-Z0-9-]+)(?P<rest>.*?)\.?$", re.I)
_PIC = re.compile(r"\bPIC(?:TURE)?\s+(?:IS\s+)?(?P<pic>\S+)", re.I)
_OCCURS = re.compile(r"\bOCCURS\s+(?P<n>\d+)(?:\s+TIMES)?", re.I)
_REDEFINES = re.compile(r"\bREDEFINES\s+(?P<target>[A-Z0-9-]+)", re.I)
_VALUE = re.compile(r"\bVALUES?\s+(?:ARE\s+|IS\s+)?(?P<values>.+)$", re.I)
_USAGE = re.compile(
    r"\b(COMP-3|COMPUTATIONAL-3|PACKED-DECIMAL|COMP-5|COMP-4|COMP|COMPUTATIONAL|BINARY)\b",
    re.I,
)


def expand_picture(picture: str) -> str:
    """Expand repeat counts: ``S9(7)V99`` -> ``S9999999V99``."""
    return re.sub(r"(.)\((\d+)\)", lambda m: m.group(1) * int(m.group(2)), picture.upper())


def describe_picture(picture: str, usage: str) -> dict:
    expanded = expand_picture(picture).rstrip(".")
    signed = expanded.startswith("S")
    body = expanded.lstrip("S")
    if set(body) <= set("9VP"):
        integer_part, _, decimal_part = body.partition("V")
        digits = integer_part.count("9") + decimal_part.count("9")
        decimals = decimal_part.count("9")
        return {
            "data_type": "numeric",
            "signed": signed,
            "digits": digits,
            "decimals": decimals,
            "byte_length": numeric_storage(digits, usage),
        }
    # Alphanumeric / edited pictures: one byte per display position
    display_positions = len(body.replace("V", ""))
    return {
        "data_type": "alphanumeric",
        "signed": False,
        "digits": None,
        "decimals": 0,
        "byte_length": display_positions,
    }


def numeric_storage(digits: int, usage: str) -> int:
    usage = usage.upper()
    if usage in {"COMP-3", "COMPUTATIONAL-3", "PACKED-DECIMAL"}:
        return digits // 2 + 1
    if usage in {"COMP", "COMPUTATIONAL", "COMP-4", "COMP-5", "BINARY"}:
        if digits <= 4:
            return 2
        if digits <= 9:
            return 4
        return 8
    return digits


def parse_copybook(source: str, name: str = "COPYBOOK") -> Copybook:
    """Parse copybook source text into a :class:`Copybook`."""
    statements = split_statements(cobol_logical_lines(source))
    roots: list[DataField] = []
    stack: list[DataField] = []

    for _, sentence in statements:
        match = _ENTRY.match(sentence.strip())
        if not match:
            continue
        level = int(match["level"])
        field_name = match["name"].upper()
        rest = match["rest"]

        if level == 88:
            if stack:
                values = _parse_values(rest)
                stack[-1].conditions.append(ConditionName(name=field_name, values=values))
            continue
        if level == 66:  # RENAMES: rare, not modelled
            continue

        field = DataField(level=level, name=field_name)
        usage_match = _USAGE.search(rest)
        if usage_match:
            field.usage = _normalise_usage(usage_match.group(1))
        pic_match = _PIC.search(rest)
        if pic_match:
            field.picture = pic_match["pic"].rstrip(".").upper()
            for key, value in describe_picture(field.picture, field.usage).items():
                setattr(field, key, value)
        occurs = _OCCURS.search(rest)
        if occurs:
            field.occurs = int(occurs["n"])
        redefines = _REDEFINES.search(rest)
        if redefines:
            field.redefines = redefines["target"].upper()

        while stack and stack[-1].level >= level:
            stack.pop()
        if stack:
            stack[-1].children.append(field)
        else:
            roots.append(field)
        stack.append(field)

    for root in roots:
        _compute_layout(root, 0)
    record_length = max((r.byte_length for r in roots), default=0)
    return Copybook(name=name.upper(), record_length=record_length, fields=roots)


def _normalise_usage(raw: str) -> str:
    raw = raw.upper()
    if raw in {"COMPUTATIONAL-3", "PACKED-DECIMAL"}:
        return "COMP-3"
    if raw in {"COMPUTATIONAL", "COMP-4", "BINARY"}:
        return "COMP"
    return raw


def _parse_values(rest: str) -> list[str]:
    match = _VALUE.search(rest)
    if not match:
        return []
    tokens = re.findall(r"'[^']*'|\"[^\"]*\"|[^\s,]+", match["values"].rstrip("."))
    return [t.strip("'\"") for t in tokens if t.upper() not in {"THRU", "THROUGH"}]


def _compute_layout(field: DataField, offset: int) -> int:
    """Assign offsets and group lengths; returns the field's total length."""
    field.offset = offset
    if field.children:
        cursor = offset
        sibling_offsets: dict[str, int] = {}
        for child in field.children:
            if child.redefines and child.redefines in sibling_offsets:
                # A REDEFINES overlays the storage of the field it names
                _compute_layout(child, sibling_offsets[child.redefines])
                continue
            sibling_offsets[child.name] = cursor
            cursor += _compute_layout(child, cursor)
        field.data_type = "group"
        single = cursor - offset
    else:
        single = field.byte_length
    total = single * (field.occurs or 1)
    field.byte_length = total
    return total


def flatten(fields: list[DataField], prefix: str = "") -> list[dict]:
    """Flatten a field tree into rows (useful for tables and CSV export)."""
    rows: list[dict] = []
    for f in fields:
        path = f"{prefix}.{f.name}" if prefix else f.name
        rows.append(
            {
                "path": path,
                "level": f.level,
                "picture": f.picture,
                "usage": f.usage,
                "type": f.data_type,
                "offset": f.offset,
                "length": f.byte_length,
                "occurs": f.occurs,
                "redefines": f.redefines,
            }
        )
        rows.extend(flatten(f.children, path))
    return rows
