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
import re
import sys
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


BOARD_ID = "esp"


def _board_ref(ref: Any, board: str | None) -> Any:
    """A connection endpoint with the board's type used as its id ("wokwi-esp32-devkit-v1:D2") -> "esp:D2"."""
    if board and isinstance(ref, str) and ref.startswith(board + ":"):
        return BOARD_ID + ref[len(board):]
    return ref


_ESCAPES = {"\\n": "\n", "\\t": "\t", "\\r": "", '\\"': '"', "\\\\": "\\"}
_ESCAPE_RE = re.compile(r"\\\\|\\n|\\t|\\r|\\\"")


def unescape_firmware(fw: str) -> str:
    """Firmware that arrived as one line full of literal backslash-n is unescaped once.

    The model sometimes escapes the sketch twice, so the JSON string holds the
    two characters backslash and n instead of a newline. Compiled as is, the
    whole sketch is one #include line and setup() never exists. When there is
    no real newline but there are literal ones, the usual escapes are undone.
    """
    if not fw or "\n" in fw or "\\n" not in fw:
        return fw
    return _ESCAPE_RE.sub(lambda m: _ESCAPES[m.group(0)], fw)


def _lowercase_ids(parts: list[dict], conns: list[tuple]) -> tuple[list[dict], list[tuple]]:
    """Part ids with capitals (rA, LED1) become lowercase everywhere, unless that would make two the same."""
    ids = [p.get("id") for p in parts]
    mapping = {i: i.lower() for i in ids if isinstance(i, str) and i != i.lower()}
    if not mapping:
        return parts, conns
    lowered = [mapping.get(i, i) for i in ids]
    if len(set(lowered)) != len(lowered):
        return parts, conns

    def ref(r):
        if isinstance(r, str) and ":" in r:
            pid, pin = r.split(":", 1)
            return f"{mapping.get(pid, pid)}:{pin}"
        return r

    return ([{**p, "id": mapping.get(p.get("id"), p.get("id"))} for p in parts],
            [(ref(a), ref(b)) for a, b in conns])


def to_design_dict(wire: dict[str, Any], *, board: str | None = None) -> dict[str, Any]:
    """Wire shape -> the dict ``ir.Design.model_validate`` expects.

    Four slips that mean the right thing are put right here instead of failing
    the schema rung for nothing electrical: "board": "esp" or the board type
    used as a connection prefix (when the board type is known), part ids with
    capital letters, and a firmware string escaped twice.
    """
    parts = []
    for p in wire.get("parts", []):
        attrs = p.get("attrs") or []
        if isinstance(attrs, list):
            attrs = {a["key"]: a["value"] for a in attrs if "key" in a}
        parts.append({"id": p.get("id"), "type": p.get("type"), "attrs": attrs})
    conns = []
    for c in wire.get("connections", []):
        if isinstance(c, dict):
            a, b = c.get("from"), c.get("to")
        else:
            a, b = (tuple(c) + (None, None))[:2]
        conns.append((_board_ref(a, board), _board_ref(b, board)))
    parts, conns = _lowercase_ids(parts, conns)
    wire_board = wire.get("board")
    if board and (not wire_board or wire_board == BOARD_ID):
        wire_board = board
    return {
        "board": wire_board,
        "parts": parts,
        "connections": conns,
        "firmware": unescape_firmware(wire.get("firmware", "")),
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


_RETRY_IN_RE = re.compile(r"try again in\s*([0-9]+(?:\.[0-9]+)?)\s*(ms|s|m)?", re.IGNORECASE)
_MAX_RETRY_WAIT_S = 45
_RETRIES_429 = 5


def retry_wait_seconds(code: int, text: str, headers: Any, attempt: int) -> float:
    """How long to wait before retrying a failed request.

    A 429 usually says how long: Groq writes "Please try again in 3.59s" in the
    body, others send a Retry-After header. That figure plus one second is used,
    capped so a stuck service does not hold a job for minutes. Anything else
    backs off 3, 5, 9 s.
    """
    wait = float(2 ** attempt + 1)
    if code == 429:
        ra = None
        try:
            ra = headers.get("Retry-After") if headers is not None else None
        except AttributeError:
            ra = None
        if ra and str(ra).strip().isdigit():
            wait = float(ra) + 1
        m = _RETRY_IN_RE.search(text or "")
        if m:
            n = float(m.group(1))
            unit = (m.group(2) or "s").lower()
            secs = n / 1000 if unit == "ms" else n * 60 if unit == "m" else n
            wait = secs + 1
    return min(wait, _MAX_RETRY_WAIT_S)


_DAILY_WAIT_CAP_S = 1800
_DAILY_WAITS_MAX = 48
_RETRY_IN_LONG_RE = re.compile(r"try again in\s*(?:(\d+)h)?(?:(\d+)m)?(?:([0-9.]+)s)?", re.IGNORECASE)


def daily_window_wait(text: str) -> float | None:
    """Seconds to wait when a daily token window is full, or None when waiting is pointless.

    Groq's daily cap is a rolling 24 hour window, so tokens come back a little
    at a time and the 429 says when ("Please try again in 14m18.8s"). A bench
    sweep that waits that long and carries on finishes by itself overnight;
    a web request must not wait, so this is used only when
    CIRCUITMIND_WAIT_FOR_QUOTA is set. Waits over half an hour are not worth it.
    """
    if not os.environ.get("CIRCUITMIND_WAIT_FOR_QUOTA"):
        return None
    m = _RETRY_IN_LONG_RE.search(text or "")
    if not m or not any(m.groups()):
        return None
    h, mi, sec = (float(x) if x else 0.0 for x in m.groups())
    wait = h * 3600 + mi * 60 + sec + 2
    return wait if wait <= _DAILY_WAIT_CAP_S else None


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
            headers={"Content-Type": "application/json", "X-goog-api-key": self.api_key,
                     "User-Agent": "circuitmind/0.1"},
            method="POST",
        )
        self.pacer.wait()
        t0 = time.time()
        last_err: Exception | None = None
        for attempt in range(_RETRIES_429 + 1):
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    data = json.loads(r.read())
                last_err = None
                break
            except urllib.error.HTTPError as e:
                text = e.read().decode(errors="replace")
                if e.code == 429 and "daily" in text.lower():
                    raise RuntimeError("Gemini daily quota exhausted; try again after the UTC reset") from e
                tries = _RETRIES_429 if e.code == 429 else 3
                if e.code in (429, 500, 503) and attempt < tries:
                    time.sleep(retry_wait_seconds(e.code, text, e.headers, attempt))
                    continue
                raise RuntimeError(f"Gemini HTTP {e.code}: {text[:400]}") from e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = e
                if attempt < 3:
                    time.sleep(2 ** attempt + 1)
                    continue
        if last_err is not None:
            raise RuntimeError(f"Gemini request failed after retries: {last_err}") from last_err
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


class OpenAICompatProvider:
    """Any OpenAI-style chat endpoint: Groq, OpenRouter, Gemini's compat layer.

    Uses JSON mode with the schema stated in the prompt, then validates with
    Pydantic downstream. json_schema mode is used when the server accepts it.
    """

    name = "openai-compat"

    def __init__(self, base_url: str, api_key: str, model: str, rpm: float = 20.0, label: str = "openai-compat"):
        if not api_key:
            raise RuntimeError(f"API key for {label} is not set")
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.name = label
        self.pacer = Pacer(rpm)
        self._schema_ok: bool | None = None

    def _post(self, body: dict) -> dict:
        req = urllib.request.Request(
            self.base_url + "/chat/completions",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}",
                     "User-Agent": "circuitmind/0.1"},
            method="POST",
        )
        last_err: Exception | None = None
        daily_waits = 0
        attempt = 0
        while attempt <= _RETRIES_429:
            try:
                with urllib.request.urlopen(req, timeout=180) as r:
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                text = e.read().decode(errors="replace")
                if e.code == 400 and "json_schema" in json.dumps(body) and "schema" in text.lower():
                    raise _SchemaUnsupported(text)
                if e.code == 429 and ("per day" in text.lower() or "daily" in text.lower()):
                    wait = daily_window_wait(text)
                    if wait is not None and daily_waits < _DAILY_WAITS_MAX:
                        daily_waits += 1
                        print(f"{self.name}: daily token window full, waiting {wait / 60:.0f} min "
                              f"({daily_waits}/{_DAILY_WAITS_MAX})", file=sys.stderr, flush=True)
                        time.sleep(wait)
                        continue
                    raise RuntimeError(f"{self.name} daily quota exhausted: {text[:200]}") from e
                tries = _RETRIES_429 if e.code == 429 else 3
                if e.code in (429, 500, 502, 503) and attempt < tries:
                    time.sleep(retry_wait_seconds(e.code, text, e.headers, attempt))
                    attempt += 1
                    continue
                raise RuntimeError(f"{self.name} HTTP {e.code}: {text[:400]}") from e
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                last_err = e
                if attempt < 3:
                    time.sleep(2 ** attempt + 1)
                    attempt += 1
                    continue
                break
        raise RuntimeError(f"{self.name} request failed after retries: {last_err}")

    def generate(self, system: str, user: str) -> ModelReply:
        schema_note = ("\n\nRespond with a single JSON object and nothing else. It must match this JSON schema:\n"
                       + json.dumps(WIRE_SCHEMA))
        messages = [{"role": "system", "content": system + schema_note}, {"role": "user", "content": user}]
        self.pacer.wait()
        t0 = time.time()
        body = {"model": self.model, "messages": messages, "temperature": 0}
        if self._schema_ok is not False:
            body["response_format"] = {"type": "json_schema",
                                       "json_schema": {"name": "design", "schema": WIRE_SCHEMA}}
        try:
            data = self._post(body)
            if self._schema_ok is None:
                self._schema_ok = True
        except _SchemaUnsupported:
            self._schema_ok = False
            body["response_format"] = {"type": "json_object"}
            data = self._post(body)
        latency = time.time() - t0
        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as e:
            raise RuntimeError(f"{self.name} returned no text: {json.dumps(data)[:400]}") from e
        u = data.get("usage", {})
        usage = Usage(tokens_in=int(u.get("prompt_tokens", 0)), tokens_out=int(u.get("completion_tokens", 0)),
                      latency_s=latency)
        text_clean = text.strip()
        if text_clean.startswith("```"):
            text_clean = text_clean.strip("`")
            if text_clean.lower().startswith("json"):
                text_clean = text_clean[4:]
        try:
            wire = json.loads(text_clean)
        except json.JSONDecodeError:
            wire = {}
        return ModelReply(wire=wire, raw=text, usage=usage, model=self.model)


class _SchemaUnsupported(Exception):
    pass


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
    if name == "groq":
        return OpenAICompatProvider(
            "https://api.groq.com/openai/v1", os.environ.get("GROQ_API_KEY", ""),
            os.environ.get("CIRCUITMIND_MODEL", "openai/gpt-oss-120b"),
            rpm=float(os.environ.get("CIRCUITMIND_MODEL_RPM", "20")), label="groq")
    if name == "openrouter":
        return OpenAICompatProvider(
            "https://openrouter.ai/api/v1", os.environ.get("OPENROUTER_API_KEY", ""),
            os.environ.get("CIRCUITMIND_MODEL", "openai/gpt-oss-120b:free"),
            rpm=float(os.environ.get("CIRCUITMIND_MODEL_RPM", "10")), label="openrouter")
    raise ValueError(f"unknown provider {name!r}")
