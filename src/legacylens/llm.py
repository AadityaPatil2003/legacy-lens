"""LLM layer: turn parsed structure into validated business-level summaries.

Design choices
- The model never sees raw source alone. It gets the parser's structured JSON
  plus the relevant source, so answers are grounded in extracted facts.
- Output must validate against :class:`ProgramSummary`; invalid JSON gets one
  repair retry, then falls back to the deterministic offline summariser.
- Providers: ``offline`` (default, no network, used in CI), ``ollama`` (local
  models such as llama3.1) and any ``openai``-compatible endpoint.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Protocol

import httpx
from pydantic import ValidationError

from legacylens.models import CobolProgram, ProgramSummary

SYSTEM_PROMPT = """You are a mainframe modernisation analyst.
You receive (1) structured facts extracted by a parser from a COBOL program and
(2) the program source. Explain what the program does in business terms.
Rules:
- Use only facts present in the input. If something is unclear, say so.
- Business rules must be concrete (conditions, thresholds, calculations).
- Return ONLY a JSON object with keys: program_id, purpose, business_rules,
  inputs, outputs, modernisation_notes. Lists are lists of short strings."""


class Summariser(Protocol):
    name: str

    def summarise(self, program: CobolProgram, source: str) -> ProgramSummary: ...


# --------------------------------------------------------------------------- #
# Offline, deterministic summariser (no LLM) - also the safety fallback
# --------------------------------------------------------------------------- #
_IF = re.compile(r"^\s*(?:IF|WHEN)\s+(.+?)\s*$", re.I)
_VERBS = (
    r"IF|ELSE|END-IF|MOVE|ADD|SUBTRACT|MULTIPLY|DIVIDE|PERFORM|COMPUTE|END-COMPUTE|WRITE|READ|"
    r"DISPLAY|EXEC|GO|STRING|CALL|SET|EVALUATE|WHEN|END-EVALUATE|ON|NOT"
)
_COMPUTE = re.compile(
    rf"COMPUTE\s+([A-Z0-9-]+)(?:\s+ROUNDED)?\s*=\s*(.+?)(?=\s+(?:{_VERBS})\b|\.(?:\s|$)|$)", re.I | re.S
)
_CONSTANT = re.compile(r"^\s*\d{2}\s+([A-Z0-9-]+)\s+PIC\S*\s+\S+\s+VALUE\s+([-+]?\.?\d[\d.]*)\s*\.", re.I)
_MESSAGE = re.compile(r"MOVE\s+'([^']+)'\s+TO", re.I)


class OfflineSummariser:
    name = "offline-rules"

    def summarise(self, program: CobolProgram, source: str) -> ProgramSummary:
        code = [line[7:72] for line in source.splitlines() if len(line) > 7 and line[6] not in "*/"]
        conditions, rules = [], []
        for line in code:
            match = _IF.match(line)
            if match and match.group(1).upper() not in {"OTHER", "EIBCALEN = 0"}:
                conditions.append(" ".join(match.group(1).split()))
        joined = " ".join(" ".join(code).split())
        constants = {m.group(1).upper(): m.group(2) for line in code if (m := _CONSTANT.match(line))}
        for target, expression in _COMPUTE.findall(joined):
            expression = " ".join(expression.split())
            used = [f"{name} = {value}" for name, value in constants.items() if name in expression.upper()]
            rules.append(
                f"{target} is calculated as {expression}" + (f" (constants: {', '.join(used)})" if used else "")
            )
        rules.extend(f"Condition checked: {c}" for c in dict.fromkeys(conditions))
        messages = list(dict.fromkeys(_MESSAGE.findall(joined)))

        inputs, outputs = [], []
        for command in program.cics_commands:
            if command.command == "RECEIVE MAP":
                inputs.append(f"Screen {command.options.get('MAPSET')}.{command.options.get('MAP')}")
            if command.command == "SEND MAP":
                outputs.append(f"Screen {command.options.get('MAPSET')}.{command.options.get('MAP')}")
            if command.command in {"READ", "READNEXT", "STARTBR"}:
                inputs.append(f"CICS file {command.options.get('FILE')}")
            if command.command in {"WRITE", "REWRITE", "DELETE"}:
                outputs.append(f"CICS file {command.options.get('FILE')}")
        for f in program.files:
            (outputs if "OUT" in f.ddname or "RPT" in f.ddname else inputs).append(
                f"File {f.logical_name} (DD {f.ddname})"
            )

        kind = "CICS online transaction program" if program.program_type == "cics-online" else "batch program"
        purpose = (
            f"{program.program_id} is a {kind} with {len(program.paragraphs)} paragraphs. "
            + (f"User-facing messages include: {'; '.join(messages[:4])}." if messages else "")
        ).strip()
        notes = [
            "Each paragraph maps naturally to a function or service method.",
            "Replace copybook-based records with typed schemas generated from the copybook JSON.",
        ]
        if program.program_type == "cics-online":
            notes.append("The SEND/RECEIVE MAP pair can become a REST endpoint plus a web form.")
        else:
            notes.append("The sequential read-process-write loop fits a streaming or chunked batch job.")
        if program.static_calls:
            notes.append(f"External dependencies to replace or wrap: {', '.join(program.static_calls)}.")
        return ProgramSummary(
            program_id=program.program_id,
            purpose=purpose,
            business_rules=rules or ["No explicit business rules detected."],
            inputs=list(dict.fromkeys(inputs)),
            outputs=list(dict.fromkeys(outputs)),
            modernisation_notes=notes,
            generated_by=self.name,
        )


# --------------------------------------------------------------------------- #
# LLM-backed summarisers
# --------------------------------------------------------------------------- #
def build_user_prompt(program: CobolProgram, source: str, max_source_chars: int = 12000) -> str:
    facts = program.model_dump(exclude={"lines_of_code"})
    return (
        "STRUCTURED FACTS (from parser):\n" + json.dumps(facts, indent=1) + "\n\nSOURCE:\n" + source[:max_source_chars]
    )


def extract_json(text: str) -> dict:
    """Pull the first JSON object out of a model response."""
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("no JSON object in response")
    return json.loads(match.group(0))


@dataclass
class ChatSummariser:
    """Works with Ollama (/api/chat) or any OpenAI-compatible /chat/completions API."""

    provider: str
    model: str
    base_url: str
    api_key: str | None = None
    timeout: float = 120.0
    fallback: Summariser = OfflineSummariser()

    @property
    def name(self) -> str:
        return f"{self.provider}:{self.model}"

    def _chat(self, messages: list[dict]) -> str:
        if self.provider == "ollama":
            response = httpx.post(
                f"{self.base_url.rstrip('/')}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0},
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()["message"]["content"]
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        response = httpx.post(
            f"{self.base_url.rstrip('/')}/chat/completions",
            headers=headers,
            json={
                "model": self.model,
                "messages": messages,
                "temperature": 0,
                "response_format": {"type": "json_object"},
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]

    def summarise(self, program: CobolProgram, source: str) -> ProgramSummary:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": build_user_prompt(program, source)},
        ]
        for attempt in range(2):
            raw = ""
            try:
                raw = self._chat(messages)
                data = extract_json(raw)
                data["program_id"] = program.program_id
                data["generated_by"] = self.name
                return ProgramSummary.model_validate(data)
            except (ValueError, ValidationError, KeyError) as error:
                if attempt == 0:  # one repair attempt with the validation error
                    messages.append({"role": "assistant", "content": raw})
                    messages.append(
                        {"role": "user", "content": f"Invalid output ({error}). Return only the JSON object."}
                    )
            except httpx.HTTPError:
                break
        summary = self.fallback.summarise(program, source)
        summary.generated_by = f"{self.fallback.name} (fallback from {self.name})"
        return summary


def get_summariser(provider: str | None = None) -> Summariser:
    provider = (provider or os.getenv("LEGACYLENS_LLM", "offline")).lower()
    if provider == "ollama":
        return ChatSummariser(
            provider="ollama",
            model=os.getenv("LEGACYLENS_MODEL", "llama3.1"),
            base_url=os.getenv("OLLAMA_URL", "http://localhost:11434"),
        )
    if provider == "openai":
        return ChatSummariser(
            provider="openai",
            model=os.getenv("LEGACYLENS_MODEL", "gpt-4o-mini"),
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            api_key=os.getenv("OPENAI_API_KEY"),
        )
    return OfflineSummariser()
