# Architecture and design decisions

## 1. Parse first, then ask the model

LLMs are good at explaining intent and poor at counting bytes. Everything that can be computed deterministically is: field offsets, packed-decimal lengths, which paragraph issues which CICS command, which dataset a job step writes. The model then receives those facts as JSON alongside the source and is asked only for what needs judgement: purpose, business rules and modernisation notes. This keeps answers checkable and cuts hallucinated field names.

## 2. Schemas everywhere

All parser output is a Pydantic model (`models.py`), so the API contract, the JSON files and the LLM output share one definition. The LLM response must validate as `ProgramSummary`. If it does not, the error is sent back once as a repair prompt. If that also fails, the deterministic summariser answers and the result is labelled `fallback`, so a flaky model never breaks a batch run.

## 3. Offline by default

The default provider needs no network or API key. That makes the tool usable on air-gapped machines (common in banks) and keeps CI deterministic. Ollama gives a fully local LLM option. Any OpenAI-compatible endpoint works for hosted models.

## 4. Mainframe details that matter

| Detail | Handling |
|---|---|
| Fixed-format columns | Sequence area (1-6) and identification area (73-80) are stripped. Column 7 `*` and `/` lines are comments. |
| COMP-3 | `digits // 2 + 1` bytes. COMP/BINARY is 2, 4 or 8 bytes by digit count. |
| REDEFINES | Overlays the named sibling's offset and does not advance the record. |
| OCCURS | Multiplies the element or group length. |
| BMS continuation | A non-blank column 72 continues the statement from column 16. |
| JCL symbolics | `&ENV.` consumes the delimiter period, so `&ENV..LOADLIB` with `ENV=PROD` gives `PROD.LOADLIB`. |
| PROC overrides | Parameters on the calling EXEC override PROC defaults. Step names become `STEP020.CALC`. |
| BMS symbolic maps | `COPY ACCTMAP` matching a BMS map is reported as the generated symbolic map, not a missing copybook. |

## 5. Flows as edge lists

Flows are plain `(source, relation, target)` edges with typed node ids (`TRAN:`, `PGM:`, `MAP:`, `FILE:`, `DSN:`, `JOB:`, `STEP:`). The same list renders as Mermaid and can be loaded into a graph database such as Neo4j for impact analysis ("which jobs write this dataset?").
