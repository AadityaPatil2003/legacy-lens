"""Pydantic models describing the structured JSON that LegacyLens produces.

Every parser returns one of these models, so the output is validated,
typed and serialisable with ``model_dump_json()``.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------- #
# Copybooks / data layouts
# --------------------------------------------------------------------------- #
class ConditionName(BaseModel):
    """A level-88 condition, e.g. ``88 CUST-ACTIVE VALUE 'A'``."""

    name: str
    values: list[str]


class DataField(BaseModel):
    level: int
    name: str
    picture: str | None = None
    usage: str = "DISPLAY"
    data_type: Literal["alphanumeric", "numeric", "group"] = "group"
    signed: bool = False
    digits: int | None = None
    decimals: int = 0
    occurs: int | None = None
    redefines: str | None = None
    byte_length: int = 0
    offset: int = 0
    conditions: list[ConditionName] = Field(default_factory=list)
    children: list[DataField] = Field(default_factory=list)


class Copybook(BaseModel):
    name: str
    record_length: int
    fields: list[DataField]


# --------------------------------------------------------------------------- #
# COBOL programs
# --------------------------------------------------------------------------- #
class CicsCommand(BaseModel):
    command: str  # e.g. "READ", "SEND MAP", "LINK"
    options: dict[str, str]
    paragraph: str | None = None


class FileDefinition(BaseModel):
    logical_name: str
    ddname: str
    organization: str | None = None


class Paragraph(BaseModel):
    name: str
    performs: list[str] = Field(default_factory=list)
    calls: list[str] = Field(default_factory=list)
    line: int


class CobolProgram(BaseModel):
    program_id: str
    program_type: Literal["cics-online", "batch"]
    copybooks: list[str]
    files: list[FileDefinition]
    paragraphs: list[Paragraph]
    cics_commands: list[CicsCommand]
    static_calls: list[str]
    sql_statements: int = 0
    lines_of_code: int


# --------------------------------------------------------------------------- #
# Screens: CICS BMS and IMS MFS
# --------------------------------------------------------------------------- #
class ScreenField(BaseModel):
    name: str | None
    row: int
    column: int
    length: int
    attributes: list[str] = Field(default_factory=list)
    initial: str | None = None
    input: bool = False


class ScreenMap(BaseModel):
    source: Literal["bms", "mfs"]
    mapset: str
    map_name: str
    size: tuple[int, int] | None = None
    fields: list[ScreenField]


class MfsMessageField(BaseModel):
    name: str | None
    literal: str | None = None
    length: int


class MfsMessage(BaseModel):
    name: str
    direction: Literal["input", "output"]
    fields: list[MfsMessageField]


class MfsFormat(BaseModel):
    screen: ScreenMap
    messages: list[MfsMessage]


# --------------------------------------------------------------------------- #
# JCL
# --------------------------------------------------------------------------- #
class DDStatement(BaseModel):
    ddname: str
    dsn: str | None = None
    disp: str | None = None
    sysout: str | None = None
    instream: bool = False


class JobStep(BaseModel):
    step_name: str
    program: str | None = None
    proc: str | None = None
    parameters: dict[str, str] = Field(default_factory=dict)
    condition: str | None = None
    dd_statements: list[DDStatement] = Field(default_factory=list)
    expanded_from_proc: str | None = None


class Job(BaseModel):
    job_name: str
    description: str | None = None
    steps: list[JobStep]


# --------------------------------------------------------------------------- #
# Cross-artefact flows and the final analysis bundle
# --------------------------------------------------------------------------- #
class FlowEdge(BaseModel):
    source: str
    target: str
    relation: str  # e.g. "sends-map", "reads-file", "runs-program", "links-to"


class Flow(BaseModel):
    name: str
    kind: Literal["online", "batch"]
    entry: str
    edges: list[FlowEdge]


class Analysis(BaseModel):
    copybooks: list[Copybook] = Field(default_factory=list)
    programs: list[CobolProgram] = Field(default_factory=list)
    screens: list[ScreenMap] = Field(default_factory=list)
    mfs_formats: list[MfsFormat] = Field(default_factory=list)
    jobs: list[Job] = Field(default_factory=list)
    flows: list[Flow] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ProgramSummary(BaseModel):
    """What the LLM layer must return for each program (validated)."""

    program_id: str
    purpose: str
    business_rules: list[str]
    inputs: list[str]
    outputs: list[str]
    modernisation_notes: list[str]
    generated_by: str
