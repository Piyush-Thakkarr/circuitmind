"""Model providers.

One interface: give it a system prompt and a user prompt, get back a dict
shaped like the wire schema below. Gemini is the real one; Mock is for
tests and offline demos.

The wire schema is deliberately flatter than ``ir.Design`` because hosted
structured-output modes do not all accept tuples, $refs or free-form
dicts. ``to_design`` converts.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol

WIRE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "board": {"type": "string"},
        "parts": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "type": {"type": "string"},
                    "attrs": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {"key": {"type": "string"}, "value": {"type": "string"}},
                            "required": ["key", "value"],
                        },
                    },
                },
                "required": ["id", "type"],
            },
        },
        "connections": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"from": {"type": "string"}, "to": {"type": "string"}},
                "required": ["from", "to"],
            },
        },
        "firmware": {"type": "string"},
        "status_line": {"type": "string"},
        "explanation": {"type": "string"},
    },
    "required": ["board", "parts", "connections", "firmware", "status_line"],
}


def to_design_dict(wire: dict[str, Any]) -> dict[str, Any]:
    """Wire shape -> the dict ``ir.Design.model_validate`` expects."""
    parts = []
    for p in wire.get("parts", []):
        attrs = p.get("attrs") or []
        if isinstance(attrs, list):
            attrs = {a["key"]: a["value"] for a in attrs if "key" in a}
        parts.append({"id": p.get("id"), "type": p.get("type"), "attrs": attrs})
    conns = []
    for c in wire.get("connections", []):
        if isinstance(c, dict):
            conns.append((c.get("from"), c.get("to")))
        else:
            conns.append(tuple(c))
    return {
        "board": wire.get("board"),
        "parts": parts,
        "connections": conns,
        "firmware": wire.get("firmware", ""),
        "status_line": wire.get("status_line", ""),
        "explanation": wire.get("explanation", ""),
    }


@dataclass
class Usage:
    tokens_in: int = 0
    tokens_out: int = 0
    latency_s: float = 0.0


@dataclass
class ModelReply:
    wire: dict[str, Any]
    raw: str
    usage: Usage = field(default_factory=Usage)
    model: str = ""


class Provider(Protocol):
    name: str

    def generate(self, system: str, user: str) -> ModelReply: ...


class Pacer:
    """Minimum spacing between requests, from an RPM figure."""

    def __init__(self, rpm: float):
        self.interval = 60.0 / rpm if rpm > 0 else 0.0
        self._last = 0.0

    def wait(self) -> None:
        now = time.monotonic()
        gap = self.interval - (now - self._last)
        if gap > 0:
            time.sleep(gap)
        self._last = time.monotonic()


class GeminiProvider:
    """Google AI Studio, native generateContent endpoint, JSON mode."""

    name = "gemini"
    URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    def __init__(self, api_key: str | None = None, model: str | None = None, rpm: float | None = None):
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("GEMINI_API_KEY is not set")
        self.model = model or os.environ.get("CIRCUITMIND_MODEL", "gemini-flash-latest")
        self.pacer = Pacer(rpm if rpm is not None else float(os.environ.get("CIRCUITMIND_MODEL_RPM", "8")))

    def generate(self, system: str, user: str) -> ModelReply:
        body = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseSchema": WIRE_SCHEMA,
            },
        }
        req = urllib.request.Request(
            self.URL.format(model=self.model),
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "X-goog-api-key": self.api_key},
            method="POST",
        )
        self.pacer.wait()
        t0 = time.time()
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=120) as r:
                    data = json.loads(r.read())
                break
            except urllib.error.HTTPError as e:
                text = e.read().decode(errors="replace")
                if e.code == 429 and "daily" in text.lower():
                    raise RuntimeError("Gemini daily quota exhausted; try again after the UTC reset") from e
                if e.code in (429, 500, 503) and attempt < 3:
                    time.sleep(2 ** attempt + 1)
                    continue
                raise RuntimeError(f"Gemini HTTP {e.code}: {text[:400]}") from e
        latency = time.time() - t0
        try:
            text = data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"Gemini returned no text: {json.dumps(data)[:400]}") from e
        meta = data.get("usageMetadata", {})
        usage = Usage(
            tokens_in=int(meta.get("promptTokenCount", 0)),
            tokens_out=int(meta.get("candidatesTokenCount", 0)),
            latency_s=latency,
        )
        try:
            wire = json.loads(text)
        except json.JSONDecodeError:
            wire = {}
        return ModelReply(wire=wire, raw=text, usage=usage, model=self.model)


class MockProvider:
    """Returns scripted replies in order. For tests and offline demos."""

    name = "mock"

    def __init__(self, replies: list[dict[str, Any]]):
        self.replies = list(replies)
        self.calls: list[tuple[str, str]] = []

    def generate(self, system: str, user: str) -> ModelReply:
        self.calls.append((system, user))
        wire = self.replies.pop(0) if self.replies else {}
        return ModelReply(wire=wire, raw=json.dumps(wire), model="mock")


def get_provider(name: str) -> Provider:
    if name == "gemini":
        return GeminiProvider()
    raise ValueError(f"unknown provider {name!r}")
