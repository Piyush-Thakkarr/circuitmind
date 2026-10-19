"""HTTP API for the web app.

POST /generate            -> {"job_id": ...}
GET  /jobs/{id}           -> job status and result
GET  /jobs/{id}/events    -> server-sent events while the job runs
GET  /catalogue           -> the part catalogue
GET  /health

Jobs run in a background thread. One at a time, which is what a laptop
demo needs. State is in memory; the run directory on disk has everything.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from . import catalogue as cat_mod
from .guide import build_guide
from .loop import run_generation
from .providers import get_provider

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "runs" / "api"

app = FastAPI(title="CircuitMind API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()
_worker_busy = threading.Semaphore(1)


class GenerateRequest(BaseModel):
    prompt: str = Field(min_length=5, max_length=2000)
    provider: str = "groq"
    attempts: int = Field(default=3, ge=1, le=3)
    simulate: bool = True


def _job(job_id: str) -> dict[str, Any]:
    with _lock:
        j = _jobs.get(job_id)
    if not j:
        raise HTTPException(404, "no such job")
    return j


def _push(job: dict[str, Any], kind: str, payload: dict[str, Any]) -> None:
    ev = {"kind": kind, "t": round(time.time() - job["started"], 1), **payload}
    job["events"].append(ev)
    for q in list(job["subscribers"]):
        q.put(ev)


def _run(job_id: str, req: GenerateRequest) -> None:
    job = _job(job_id)
    with _worker_busy:
        job["status"] = "running"
        _push(job, "status", {"status": "running"})
        try:
            cat = cat_mod.load()
            prov = get_provider(req.provider)
            workdir = RUNS / job_id
            workdir.mkdir(parents=True, exist_ok=True)

            def on_event(kind: str, p: dict[str, Any]) -> None:
                _push(job, kind, p)

            def scenario_for(design, adir: Path) -> Path:
                """Wait for the design's own status line. Press every button first."""
                steps = ["  - delay: 500ms"]
                for part in design.parts:
                    if part.type == "wokwi-pushbutton":
                        steps.append(f"  - set-control:\n      part-id: {part.id}\n      control: pressed\n      value: 1")
                steps.append(f"  - wait-serial: {json.dumps(design.status_line)}")
                scen = adir / "scenario.yaml"
                scen.write_text("name: web\nversion: 1\nauthor: circuitmind\nsteps:\n" + "\n".join(steps) + "\n")
                return scen

            res = run_generation(
                req.prompt, prov, cat, workdir,
                max_attempts=req.attempts, simulate=req.simulate, timeout_ms=8000,
                grounded=True, use_feedback=True, on_event=on_event,
                scenario_factory=scenario_for,
            )
            final = res.final
            passed = res.passed
            sim_result: dict[str, Any] | None = None
            if final:
                for r in final.outcome.results:
                    if r.rung.value == "simulate":
                        sim_result = {"passed": r.passed, "rung": "simulate", "summary": r.summary, "detail": r.detail}

            result: dict[str, Any] = {
                "passed": passed,
                "attempts": [
                    {"n": a.n, "passed": a.passed, "failed_rung": a.failed_rung,
                     "feedback": a.feedback,
                     "rungs": [{"rung": r.rung.value, "passed": r.passed, "summary": r.summary,
                                "detail": r.detail, "seconds": round(r.seconds, 1)} for r in a.outcome.results]}
                    for a in res.attempts
                ],
                "simulation": sim_result,
                "model": final.reply.model if final else "",
                "tokens": dict(zip(("in", "out"), res.tokens())),
            }
            if final and final.design:
                d = final.design
                result["design"] = json.loads(d.model_dump_json())
                result["diagram_json"] = final.outcome.diagram_json
                result["guide"] = build_guide(d, cat, verified=passed)
            job["result"] = result
            job["status"] = "done" if passed else "failed"
        except Exception as e:  # noqa: BLE001
            job["status"] = "error"
            job["error"] = str(e)[:500]
        finally:
            _push(job, "status", {"status": job["status"], "error": job.get("error")})
            _push(job, "end", {})


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "catalogue": cat_mod.load().hash,
            "providers": {"groq": bool(os.environ.get("GROQ_API_KEY")),
                          "gemini": bool(os.environ.get("GEMINI_API_KEY"))},
            "wokwi": bool(os.environ.get("WOKWI_CLI_TOKEN"))}


@app.get("/catalogue")
def catalogue() -> dict[str, Any]:
    c = cat_mod.load()
    return {"hash": c.hash, "parts": c.parts}


@app.post("/generate")
def generate(req: GenerateRequest) -> dict[str, str]:
    if req.simulate and not os.environ.get("WOKWI_CLI_TOKEN"):
        raise HTTPException(400, "WOKWI_CLI_TOKEN is not set on the server")
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {"id": job_id, "status": "queued", "prompt": req.prompt, "started": time.time(),
                         "events": [], "subscribers": [], "result": None, "error": None}
    threading.Thread(target=_run, args=(job_id, req), daemon=True).start()
    return {"job_id": job_id}


@app.get("/jobs/{job_id}")
def job_status(job_id: str) -> dict[str, Any]:
    j = _job(job_id)
    return {"id": j["id"], "status": j["status"], "prompt": j["prompt"], "result": j["result"],
            "error": j["error"], "events": j["events"]}


@app.get("/jobs/{job_id}/events")
def job_events(job_id: str) -> StreamingResponse:
    j = _job(job_id)
    q: queue.Queue = queue.Queue()
    for ev in j["events"]:
        q.put(ev)
    j["subscribers"].append(q)

    def gen():
        try:
            while True:
                try:
                    ev = q.get(timeout=15)
                except queue.Empty:
                    yield ": keepalive\n\n"
                    continue
                yield f"data: {json.dumps(ev)}\n\n"
                if ev.get("kind") == "end":
                    break
        finally:
            if q in j["subscribers"]:
                j["subscribers"].remove(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
