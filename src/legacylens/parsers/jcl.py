"""Parse JCL jobs and catalogued procedures, expanding PROC calls.

Supports JOB / EXEC PGM= / EXEC <proc> / DD statements, continuation lines,
in-stream data, COND=, and symbolic parameter substitution
(``&ENV..LOADLIB`` with ``ENV=PROD`` -> ``PROD.LOADLIB``).
"""

from __future__ import annotations

import re

from legacylens.models import DDStatement, Job, JobStep

_PARAM = re.compile(r"([A-Z0-9]+)=((?:\([^)]*\))|(?:'[^']*')|[^,]+)", re.I)


def _jcl_statements(source: str) -> list[tuple[str | None, str, str, str]]:
    """Return (name, operation, operands, comment_text) for each JCL statement."""
    statements: list[tuple[str | None, str, str, str]] = []
    pending: list[str] | None = None
    comments: list[str] = []
    in_stream = False

    for raw in source.splitlines():
        line = raw.rstrip()
        if in_stream:
            if line.startswith("/*") or line.startswith("//"):
                in_stream = False
                if line.startswith("/*"):
                    continue
            else:
                continue
        if line.startswith("//*"):
            comments.append(line[3:].strip())
            continue
        if not line.startswith("//"):
            continue
        body = line[2:72]
        if pending is not None and body.startswith(" "):
            pending[2] += body.strip()
            if not pending[2].endswith(","):
                statements.append(tuple(pending))  # type: ignore[arg-type]
                pending = None
            continue
        if pending is not None:
            statements.append(tuple(pending))  # type: ignore[arg-type]
            pending = None
        name = None
        if not body.startswith(" "):
            name, _, body = body.partition(" ")
        parts = body.strip().split(None, 1)
        if not parts:
            continue
        op = parts[0].upper()
        operands = parts[1].split("  ")[0].strip() if len(parts) > 1 else ""
        record = [name, op, operands, " ".join(comments)]
        comments = []
        if operands.rstrip().endswith("*") and op == "DD" and operands.strip() in {"*", "DATA"}:
            in_stream = True
        if operands.strip() in {"*", "DATA"}:
            in_stream = True
        if operands.endswith(","):
            pending = record
        else:
            statements.append(tuple(record))  # type: ignore[arg-type]
    if pending is not None:
        statements.append(tuple(pending))  # type: ignore[arg-type]
    return statements


def _params(operands: str) -> dict[str, str]:
    return {k.upper(): v.strip("'") for k, v in _PARAM.findall(operands)}


def substitute(text: str | None, symbols: dict[str, str]) -> str | None:
    if text is None:
        return None

    def repl(match: re.Match[str]) -> str:
        name = match.group(1).upper()
        return symbols.get(name, match.group(0))

    # &NAME. (the period is a delimiter and is consumed) or &NAME
    return re.sub(r"&([A-Z0-9]+)\.?", repl, text)


def _dd(name: str, operands: str) -> DDStatement:
    params = _params(operands)
    return DDStatement(
        ddname=name.upper(),
        dsn=params.get("DSN") or params.get("DSNAME"),
        disp=params.get("DISP"),
        sysout=params.get("SYSOUT"),
        instream=operands.strip() in {"*", "DATA"},
    )


def parse_proc(source: str) -> tuple[str, dict[str, str], list[JobStep]]:
    """Parse a catalogued procedure: returns (name, default symbols, steps)."""
    name, defaults, steps = "UNKNOWN", {}, []
    current: JobStep | None = None
    for stmt_name, op, operands, _ in _jcl_statements(source):
        if op == "PROC":
            name = (stmt_name or name).upper()
            defaults = _params(operands)
        elif op == "EXEC":
            current = _exec_step(stmt_name, operands)
            steps.append(current)
        elif op == "DD" and current is not None and stmt_name:
            current.dd_statements.append(_dd(stmt_name, operands))
    return name, defaults, steps


def _exec_step(name: str | None, operands: str) -> JobStep:
    params = _params(operands)
    first = operands.split(",")[0].strip()
    step = JobStep(step_name=(name or "").upper(), condition=params.pop("COND", None))
    if "PGM" in params:
        step.program = params.pop("PGM").upper()
    elif "PROC" in params:
        step.proc = params.pop("PROC").upper()
    elif "=" not in first:
        step.proc = first.upper()
    step.parameters = params
    return step


def parse_jcl(source: str, procs: dict[str, str] | None = None) -> Job:
    """Parse a job. ``procs`` maps PROC name -> PROC source for expansion."""
    procs = {k.upper(): v for k, v in (procs or {}).items()}
    job_name, description = "UNKNOWN", None
    steps: list[JobStep] = []
    current: JobStep | None = None

    for stmt_name, op, operands, comment in _jcl_statements(source):
        if op == "JOB":
            job_name = (stmt_name or job_name).upper()
            quoted = re.search(r"'([^']*)'", operands)
            description = quoted.group(1) if quoted else (comment or None)
        elif op == "EXEC":
            current = _exec_step(stmt_name, operands)
            if current.proc and current.proc in procs:
                steps.extend(_expand(current, procs[current.proc]))
                current = None
            else:
                steps.append(current)
        elif op == "DD" and current is not None and stmt_name:
            current.dd_statements.append(_dd(stmt_name, operands))
    return Job(job_name=job_name, description=description, steps=steps)


def _expand(call: JobStep, proc_source: str) -> list[JobStep]:
    proc_name, defaults, proc_steps = parse_proc(proc_source)
    symbols = {**defaults, **call.parameters}
    expanded = []
    for step in proc_steps:
        new = step.model_copy(deep=True)
        new.step_name = f"{call.step_name}.{step.step_name}"
        new.expanded_from_proc = proc_name
        new.parameters = {k: substitute(v, symbols) or "" for k, v in step.parameters.items()}
        for dd in new.dd_statements:
            dd.dsn = substitute(dd.dsn, symbols)
        if new.condition is None:
            new.condition = call.condition
        expanded.append(new)
    return expanded
