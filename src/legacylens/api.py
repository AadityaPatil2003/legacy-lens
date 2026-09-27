"""FastAPI service: upload legacy artefacts, get structured JSON and a report back."""

from __future__ import annotations

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel

from legacylens import __version__
from legacylens.analyzer import analyze_sources, classify
from legacylens.llm import get_summariser
from legacylens.models import Analysis, ProgramSummary
from legacylens.report import render_report

MAX_FILE_BYTES = 2_000_000

app = FastAPI(
    title="LegacyLens",
    version=__version__,
    description="Turn COBOL, copybooks, CICS BMS, IMS MFS and JCL into structured JSON "
    "and LLM-grounded comprehension documents.",
)


class SummaryResponse(BaseModel):
    analysis: Analysis
    summaries: list[ProgramSummary]


async def _read(files: list[UploadFile]) -> dict[str, str]:
    sources: dict[str, str] = {}
    for upload in files:
        name = upload.filename or "unnamed"
        if not classify(name):
            raise HTTPException(status_code=415, detail=f"Unsupported file type: {name}")
        data = await upload.read()
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(status_code=413, detail=f"{name} is larger than {MAX_FILE_BYTES} bytes")
        sources[name] = data.decode("utf-8", errors="replace")
    if not sources:
        raise HTTPException(status_code=400, detail="Upload at least one file")
    return sources


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.post("/analyze", response_model=Analysis)
async def analyze(files: list[UploadFile] = File(...)) -> Analysis:
    analysis, _ = analyze_sources(await _read(files))
    return analysis


@app.post("/summarize", response_model=SummaryResponse)
async def summarize(
    files: list[UploadFile] = File(...),
    llm: str | None = Query(None, description="offline | ollama | openai (default from LEGACYLENS_LLM)"),
) -> SummaryResponse:
    analysis, sources = analyze_sources(await _read(files))
    summariser = get_summariser(llm)
    summaries = [summariser.summarise(p, sources[p.program_id]) for p in analysis.programs]
    return SummaryResponse(analysis=analysis, summaries=summaries)


@app.post("/report", response_class=PlainTextResponse)
async def report(files: list[UploadFile] = File(...), llm: str | None = Query(None)) -> str:
    analysis, sources = analyze_sources(await _read(files))
    summariser = get_summariser(llm)
    summaries = [summariser.summarise(p, sources[p.program_id]) for p in analysis.programs]
    return render_report(analysis, summaries)
