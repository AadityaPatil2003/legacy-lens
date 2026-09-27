"""Extract structure from a COBOL program.

Pulls out PROGRAM-ID, COPY members, FILE-CONTROL selects, paragraphs with
their PERFORM / CALL edges, embedded ``EXEC CICS`` commands (with options)
and a count of ``EXEC SQL`` blocks. It is a pragmatic, regex-driven scanner,
not a full COBOL grammar, which is enough to build call graphs and feed an
LLM grounded, structured context.
"""

from __future__ import annotations

import re

from legacylens.models import CicsCommand, CobolProgram, FileDefinition, Paragraph
from legacylens.parsers.common import cobol_logical_lines

_PROGRAM_ID = re.compile(r"PROGRAM-ID\.\s*([A-Z0-9-]+)", re.I)
_COPY = re.compile(r"\bCOPY\s+([A-Z0-9-]+)", re.I)
_SELECT = re.compile(
    r"SELECT\s+(?P<name>[A-Z0-9-]+)\s+ASSIGN\s+TO\s+(?P<dd>[A-Z0-9-]+)"
    r"(?:.*?ORGANIZATION\s+IS\s+(?P<org>[A-Z]+))?",
    re.I,
)
_PARAGRAPH = re.compile(r"^([A-Z0-9][A-Z0-9-]*)\.\s*$", re.I)
_PERFORM = re.compile(r"\bPERFORM\s+([A-Z0-9][A-Z0-9-]*)", re.I)
_CALL = re.compile(r"\bCALL\s+'([A-Z0-9-]+)'", re.I)
_EXEC_BLOCK = re.compile(r"EXEC\s+(CICS|SQL)\s+(.*?)\s*END-EXEC", re.I | re.S)
_OPTION = re.compile(r"([A-Z][A-Z0-9-]*)(?:\s*\(\s*([^)]*?)\s*\))?", re.I)

# CICS commands whose name is two words
_TWO_WORD_COMMANDS = {
    ("SEND", "MAP"),
    ("RECEIVE", "MAP"),
    ("SEND", "TEXT"),
    ("START", "TRANSID"),
    ("HANDLE", "CONDITION"),
    ("HANDLE", "AID"),
}
_PERFORM_KEYWORDS = {"UNTIL", "VARYING", "WITH", "TEST", "TIMES"}


def parse_cobol(source: str) -> CobolProgram:
    lines = cobol_logical_lines(source)
    joined = "\n".join(code for _, code in lines)

    program_id_match = _PROGRAM_ID.search(joined)
    program_id = program_id_match.group(1).upper() if program_id_match else "UNKNOWN"

    copybooks = sorted({m.upper() for m in _COPY.findall(joined)})
    files = [
        FileDefinition(
            logical_name=m["name"].upper(),
            ddname=m["dd"].upper(),
            organization=(m["org"] or None) and m["org"].upper(),
        )
        for m in _SELECT.finditer(" ".join(joined.split()))
    ]

    paragraphs, paragraph_of_line = _paragraphs(lines)
    cics_commands, sql_count = _exec_blocks(lines, paragraph_of_line)
    static_calls = sorted({c for p in paragraphs for c in p.calls})

    program_type = "cics-online" if cics_commands else "batch"
    return CobolProgram(
        program_id=program_id,
        program_type=program_type,
        copybooks=copybooks,
        files=files,
        paragraphs=paragraphs,
        cics_commands=cics_commands,
        static_calls=static_calls,
        sql_statements=sql_count,
        lines_of_code=len(lines),
    )


def _paragraphs(lines: list[tuple[int, str]]) -> tuple[list[Paragraph], dict[int, str]]:
    in_procedure = False
    current: Paragraph | None = None
    paragraphs: list[Paragraph] = []
    paragraph_of_line: dict[int, str] = {}

    for number, code in lines:
        text = code.strip()
        if re.match(r"PROCEDURE\s+DIVISION", text, re.I):
            in_procedure = True
            continue
        if not in_procedure:
            continue
        # Paragraph headers start in Area A (column 8 -> index 0 of code area)
        header = _PARAGRAPH.match(text)
        if header and not code.startswith("    "):
            current = Paragraph(name=header.group(1).upper(), line=number)
            paragraphs.append(current)
            continue
        if current is None:
            continue
        paragraph_of_line[number] = current.name
        for target in _PERFORM.findall(text):
            target = target.upper()
            if target not in _PERFORM_KEYWORDS and target not in current.performs:
                current.performs.append(target)
        for called in _CALL.findall(text):
            if called.upper() not in current.calls:
                current.calls.append(called.upper())
    return paragraphs, paragraph_of_line


def _exec_blocks(lines: list[tuple[int, str]], paragraph_of_line: dict[int, str]) -> tuple[list[CicsCommand], int]:
    # Keep a marker of the originating line so each command knows its paragraph
    tagged = "\n".join(f"@@{number}@@ {code}" for number, code in lines)
    commands: list[CicsCommand] = []
    sql_count = 0
    for match in _EXEC_BLOCK.finditer(tagged):
        kind = match.group(1).upper()
        markers = re.findall(r"@@(\d+)@@", tagged[: match.start()])
        start_line = int(markers[-1]) if markers else 0
        body = re.sub(r"@@\d+@@", " ", match.group(2))
        body = " ".join(body.split())
        if kind == "SQL":
            sql_count += 1
            continue
        commands.append(_parse_cics(body, paragraph_of_line.get(start_line)))
    return commands, sql_count


def _parse_cics(body: str, paragraph: str | None) -> CicsCommand:
    tokens = [(m.group(1).upper(), m.group(2)) for m in _OPTION.finditer(body)]
    if not tokens:
        return CicsCommand(command="UNKNOWN", options={}, paragraph=paragraph)
    first = tokens[0][0]
    command = first
    option_tokens = tokens[1:]
    if len(tokens) > 1 and (first, tokens[1][0]) in _TWO_WORD_COMMANDS:
        # e.g. SEND MAP('ACCTMAP') -> command "SEND MAP", option MAP=ACCTMAP
        command = f"{first} {tokens[1][0]}"
        option_tokens = tokens[1:]
    options = {name: (value or "").strip("'\"") for name, value in option_tokens}
    return CicsCommand(command=command, options=options, paragraph=paragraph)
