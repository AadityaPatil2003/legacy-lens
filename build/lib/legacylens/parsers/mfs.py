"""Parse IMS MFS source (FMT / DFLD and MSG / MFLD) into screen + message JSON."""

from __future__ import annotations

import re

from legacylens.models import MfsFormat, MfsMessage, MfsMessageField, ScreenField, ScreenMap

_KEYVAL = re.compile(r"([A-Z]+)=((?:\((?:[^()]|\([^)]*\))*\))|[^,\s]+)", re.I)
_LITERAL = re.compile(r"^'((?:[^']|'')*)'")


def _statements(source: str) -> list[tuple[str | None, str, str]]:
    result = []
    for raw in source.splitlines():
        if not raw.strip() or raw.startswith("*"):
            continue
        label = None
        text = raw.rstrip()
        if not text.startswith(" "):
            label, _, text = text.partition(" ")
        parts = text.strip().split(None, 1)
        result.append((label, parts[0].upper(), parts[1] if len(parts) > 1 else ""))
    return result


def _pos(value: str) -> tuple[int, int]:
    nums = [int(n) for n in re.findall(r"\d+", value)]
    return (nums[0], nums[1]) if len(nums) >= 2 else (0, 0)


def parse_mfs(source: str) -> list[MfsFormat]:
    formats: list[MfsFormat] = []
    screen: ScreenMap | None = None
    messages: list[MfsMessage] = []
    message: MfsMessage | None = None

    for label, op, operands in _statements(source):
        opts = {k.upper(): v for k, v in _KEYVAL.findall(operands)}
        if op == "FMT":
            screen = ScreenMap(source="mfs", mapset=(label or "").upper(), map_name=(label or "").upper(), fields=[])
        elif op == "DFLD" and screen is not None:
            literal = _LITERAL.match(operands.strip())
            row, col = _pos(opts.get("POS", ""))
            attributes = [a.upper() for a in re.findall(r"[A-Z]+", opts.get("ATTR", ""))]
            length = int(opts.get("LTH", len(literal.group(1)) if literal else 0))
            screen.fields.append(
                ScreenField(
                    name=label.upper() if label else None,
                    row=row,
                    column=col,
                    length=length,
                    attributes=attributes,
                    initial=literal.group(1) if literal else None,
                    input="MOD" in attributes or ("PROT" not in attributes and label is not None and not literal),
                )
            )
        elif op == "MSG":
            direction = "input" if "INPUT" in opts.get("TYPE", "").upper() else "output"
            message = MfsMessage(name=(label or "").upper(), direction=direction, fields=[])
            messages.append(message)
        elif op == "MFLD" and message is not None:
            literal = _LITERAL.match(operands.strip())
            name = None if literal else operands.split(",")[0].strip().upper() or None
            message.fields.append(
                MfsMessageField(
                    name=name,
                    literal=literal.group(1).rstrip() if literal else None,
                    length=int(opts.get("LTH", "0")),
                )
            )
        elif op == "END" and screen is not None:
            formats.append(MfsFormat(screen=screen, messages=messages))
            screen, messages, message = None, [], None
    if screen is not None:
        formats.append(MfsFormat(screen=screen, messages=messages))
    return formats
