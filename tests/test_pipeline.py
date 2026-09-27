import json

import httpx
from fastapi.testclient import TestClient

from legacylens.analyzer import analyze_directory
from legacylens.api import app
from legacylens.llm import ChatSummariser, OfflineSummariser
from legacylens.report import render_report


def test_end_to_end_flows(samples):
    analysis, sources = analyze_directory(samples)
    assert len(analysis.programs) == 2 and len(analysis.jobs) == 1
    online = next(f for f in analysis.flows if f.kind == "online")
    relations = {(e.source, e.relation, e.target) for e in online.edges}
    assert ("TRAN:AINQ", "starts", "PGM:ACCTINQ") in relations
    assert ("PGM:ACCTINQ", "reads-file", "FILE:CUSTMAST") in relations
    batch = next(f for f in analysis.flows if f.kind == "batch")
    assert any(e.target == "DSN:PROD.INT.EXCEPTIONS" and e.relation == "writes-dataset" for e in batch.edges)
    assert any("symbolic map" in w for w in analysis.warnings)


def test_offline_summary_extracts_rules(samples):
    analysis, sources = analyze_directory(samples)
    program = next(p for p in analysis.programs if p.program_id == "INTCALC")
    summary = OfflineSummariser().summarise(program, sources["INTCALC"])
    assert any("WS-RATE-RETAIL = .0125" in rule for rule in summary.business_rules)


def test_llm_summary_is_validated_and_falls_back(samples, monkeypatch):
    analysis, sources = analyze_directory(samples)
    program = analysis.programs[0]
    good = {
        "purpose": "Shows a customer's balance and available credit.",
        "business_rules": ["Closed accounts are rejected"],
        "inputs": ["Customer ID"],
        "outputs": ["Account screen"],
        "modernisation_notes": ["Expose as GET /customers/{id}"],
    }

    def fake_post(url, **kwargs):
        return httpx.Response(200, json={"message": {"content": json.dumps(good)}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", fake_post)
    llm = ChatSummariser(provider="ollama", model="test", base_url="http://llm")
    summary = llm.summarise(program, sources[program.program_id])
    assert summary.purpose.startswith("Shows") and summary.generated_by == "ollama:test"

    def broken_post(url, **kwargs):
        return httpx.Response(200, json={"message": {"content": "not json"}}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", broken_post)
    fallback = llm.summarise(program, sources[program.program_id])
    assert "fallback" in fallback.generated_by


def test_report_renders_mermaid(samples):
    analysis, sources = analyze_directory(samples)
    report = render_report(analysis)
    assert "```mermaid" in report and "CUSTREC" in report


def test_api(samples):
    client = TestClient(app)
    assert client.get("/health").json()["status"] == "ok"
    files = [("files", (p.name, p.read_bytes())) for p in samples.rglob("*") if p.is_file()]
    response = client.post("/summarize?llm=offline", files=files)
    assert response.status_code == 200
    body = response.json()
    assert {s["program_id"] for s in body["summaries"]} == {"ACCTINQ", "INTCALC"}
    bad = client.post("/analyze", files=[("files", ("notes.txt", b"hello"))])
    assert bad.status_code == 415
