"""Run every parser over a set of source files and stitch the results together."""

from __future__ import annotations

from pathlib import Path

from legacylens.flows import batch_flows, online_flows
from legacylens.models import Analysis
from legacylens.parsers import parse_bms, parse_cobol, parse_copybook, parse_jcl, parse_mfs

KINDS = {
    ".cbl": "cobol",
    ".cob": "cobol",
    ".cobol": "cobol",
    ".cpy": "copybook",
    ".copy": "copybook",
    ".bms": "bms",
    ".mfs": "mfs",
    ".jcl": "jcl",
    ".proc": "proc",
    ".prc": "proc",
}


def classify(filename: str) -> str | None:
    return KINDS.get(Path(filename).suffix.lower())


def analyze_sources(files: dict[str, str]) -> tuple[Analysis, dict[str, str]]:
    """Analyse ``{filename: text}``. Returns the analysis and program sources by id."""
    analysis = Analysis()
    procs: dict[str, str] = {}
    jcl_sources: list[tuple[str, str]] = []
    program_sources: dict[str, str] = {}

    for filename, text in sorted(files.items()):
        kind = classify(filename)
        stem = Path(filename).stem.upper()
        try:
            if kind == "copybook":
                analysis.copybooks.append(parse_copybook(text, stem))
            elif kind == "cobol":
                program = parse_cobol(text)
                analysis.programs.append(program)
                program_sources[program.program_id] = text
            elif kind == "bms":
                analysis.screens.extend(parse_bms(text))
            elif kind == "mfs":
                analysis.mfs_formats.extend(parse_mfs(text))
            elif kind == "proc":
                procs[stem] = text
            elif kind == "jcl":
                jcl_sources.append((filename, text))
            else:
                analysis.warnings.append(f"Skipped {filename}: unknown file type")
        except Exception as error:  # keep going; report per-file failures
            analysis.warnings.append(f"Failed to parse {filename}: {error}")

    for filename, text in jcl_sources:
        try:
            analysis.jobs.append(parse_jcl(text, procs))
        except Exception as error:
            analysis.warnings.append(f"Failed to parse {filename}: {error}")

    known_copybooks = {c.name for c in analysis.copybooks}
    symbolic_maps = {s.map_name for s in analysis.screens}
    for program in analysis.programs:
        for member in program.copybooks:
            if member in known_copybooks:
                continue
            if member in symbolic_maps:
                analysis.warnings.append(
                    f"{program.program_id}: COPY {member} is the BMS symbolic map (generated from the mapset)"
                )
            else:
                analysis.warnings.append(f"{program.program_id}: copybook {member} not supplied")

    analysis.flows = online_flows(analysis.programs) + batch_flows(analysis.jobs, analysis.programs)
    return analysis, program_sources


def analyze_directory(path: str | Path) -> tuple[Analysis, dict[str, str]]:
    root = Path(path)
    files = {
        str(p.relative_to(root)): p.read_text(encoding="utf-8", errors="replace")
        for p in sorted(root.rglob("*"))
        if p.is_file() and classify(p.name)
    }
    return analyze_sources(files)
