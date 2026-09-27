"""Command line: ``legacylens analyze samples/ --out output/ --llm offline``."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from legacylens.analyzer import analyze_directory
from legacylens.llm import get_summariser
from legacylens.report import render_report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="legacylens", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("analyze", help="analyse a folder of legacy artefacts")
    run.add_argument("path", type=Path)
    run.add_argument("--out", type=Path, default=Path("output"))
    run.add_argument("--llm", default=None, help="offline | ollama | openai")
    args = parser.parse_args(argv)

    analysis, sources = analyze_directory(args.path)
    summariser = get_summariser(args.llm)
    summaries = [summariser.summarise(p, sources[p.program_id]) for p in analysis.programs]

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "analysis.json").write_text(analysis.model_dump_json(indent=2))
    (args.out / "summaries.json").write_text(json.dumps([s.model_dump() for s in summaries], indent=2))
    (args.out / "REPORT.md").write_text(render_report(analysis, summaries))
    print(
        f"Analysed {len(analysis.programs)} programs, {len(analysis.copybooks)} copybooks, "
        f"{len(analysis.screens) + len(analysis.mfs_formats)} screens, {len(analysis.jobs)} jobs "
        f"-> {args.out}/ (summaries by {summariser.name})"
    )
    for warning in analysis.warnings:
        print(f"  warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
