"""Parse CICS BMS mapset macros (DFHMSD / DFHMDI / DFHMDF) into screen JSON."""

from __future__ import annotations

import re

from legacylens.models import ScreenField, ScreenMap

_KEYVAL = re.compile(r"([A-Z]+)=((?:\([^)]*\))|(?:'(?:[^']|'')*')|[^,\s]+)", re.I)


def _assembler_statements(source: str) -> list[tuple[str | None, str, str]]:
    """Join assembler continuation lines and split into (label, op, operands).

    Continuation: a non-blank character in column 72 means the statement
    continues on the next line, starting in column 16.
    """
    statements: list[tuple[str | None, str, str]] = []
    buffer = ""
    for raw in source.splitlines():
        if not raw.strip() or raw.startswith("*"):
            continue
        line = raw.ljust(72)
        continued = len(raw) >= 72 and raw[71] not in (" ", "")
        text = line[:71].rstrip()
        if buffer:
            text = text.strip()
        buffer += text
        if continued:
            continue
        statements.append(_split(buffer))
        buffer = ""
    if buffer:
        statements.append(_split(buffer))
    return statements


def _split(statement: str) -> tuple[str | None, str, str]:
    label = None
    if not statement.startswith(" "):
        label, _, statement = statement.partition(" ")
    parts = statement.strip().split(None, 1)
    op = parts[0].upper() if parts else ""
    operands = parts[1] if len(parts) > 1 else ""
    return label, op, operands


def _options(operands: str) -> dict[str, str]:
    return {k.upper(): v for k, v in _KEYVAL.findall(operands)}


def _tuple(value: str) -> list[str]:
    return [v.strip() for v in value.strip("()").split(",") if v.strip()]


def parse_bms(source: str) -> list[ScreenMap]:
    maps: list[ScreenMap] = []
    mapset = "UNKNOWN"
    current: ScreenMap | None = None
    for label, op, operands in _assembler_statements(source):
        opts = _options(operands)
        if op == "DFHMSD":
            if opts.get("TYPE", "").upper() == "FINAL":
                continue
            mapset = (label or mapset).upper()
        elif op == "DFHMDI":
            size = None
            if "SIZE" in opts:
                rows, cols = (int(x) for x in _tuple(opts["SIZE"]))
                size = (rows, cols)
            current = ScreenMap(source="bms", mapset=mapset, map_name=(label or "").upper(), size=size, fields=[])
            maps.append(current)
        elif op == "DFHMDF" and current is not None:
            row, col = (int(x) for x in _tuple(opts.get("POS", "(0,0)")))
            attributes = [a.upper() for a in _tuple(opts.get("ATTRB", ""))]
            initial = opts.get("INITIAL")
            current.fields.append(
                ScreenField(
                    name=label.upper() if label else None,
                    row=row,
                    column=col,
                    length=int(opts.get("LENGTH", "0")),
                    attributes=attributes,
                    initial=initial.strip("'").replace("''", "'") if initial else None,
                    input="UNPROT" in attributes,
                )
            )
    return maps
