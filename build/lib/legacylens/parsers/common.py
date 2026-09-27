"""Helpers shared by the COBOL-family parsers."""

from __future__ import annotations

import re

SEQUENCE_AREA = slice(0, 6)
INDICATOR_COLUMN = 6
CODE_AREA = slice(7, 72)


def cobol_logical_lines(source: str) -> list[tuple[int, str]]:
    """Return (line_number, code) pairs from fixed-format COBOL source.

    Drops the sequence area (cols 1-6) and the identification area (73-80),
    skips comment lines (``*`` or ``/`` in column 7) and blank lines.
    Line numbers are 1-based and refer to the original file.
    """
    result: list[tuple[int, str]] = []
    for number, raw in enumerate(source.splitlines(), start=1):
        line = raw.rstrip("\n")
        if len(line) > INDICATOR_COLUMN and line[INDICATOR_COLUMN] in "*/":
            continue
        code = line[CODE_AREA] if len(line) > 7 else ""
        if code.strip():
            result.append((number, code.rstrip()))
    return result


def split_statements(lines: list[tuple[int, str]]) -> list[tuple[int, str]]:
    """Join logical lines into period-terminated sentences.

    Returns (first_line_number, sentence_text) with whitespace collapsed.
    """
    sentences: list[tuple[int, str]] = []
    buffer: list[str] = []
    start = 0
    for number, code in lines:
        if not buffer:
            start = number
        buffer.append(code.strip())
        if _ends_sentence(code):
            sentences.append((start, re.sub(r"\s+", " ", " ".join(buffer)).strip()))
            buffer = []
    if buffer:
        sentences.append((start, re.sub(r"\s+", " ", " ".join(buffer)).strip()))
    return sentences


def _ends_sentence(code: str) -> bool:
    stripped = _strip_literals(code).rstrip()
    return stripped.endswith(".")


def _strip_literals(text: str) -> str:
    return re.sub(r"'[^']*'|\"[^\"]*\"", "''", text)
