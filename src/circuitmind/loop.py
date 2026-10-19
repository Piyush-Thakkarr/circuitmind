"""The generate-check-correct loop.

Ask the model for a design, run it up the ladder, and if it fails send the
failure and the previous attempt back. Bounded by ``max_attempts``.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import ValidationError

from .catalogue import Catalogue
from .harness import LadderOutcome, run_ladder
from .harness.types import Rung, RungResult
from .ir import Design
from .prompt import SYSTEM, build_retry_prompt, build_user_prompt
from .providers import ModelReply, Provider, to_design_dict


@dataclass
class Attempt:
    n: int
    reply: ModelReply
    design: Design | None
    outcome: LadderOutcome
    feedback: str
    seconds: float

    @property
    def passed(self) -> bool:
        return self.outcome.passed

    @property
    def failed_rung(self) -> str:
        r = self.outcome.failed_rung
        return r.value if r else ""


@dataclass
class RunResult:
    request: str
    attempts: list[Attempt] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return bool(self.attempts) and self.attempts[-1].passed

    @property
    def final(self) -> Attempt | None:
        return self.attempts[-1] if self.attempts else None

    def tokens(self) -> tuple[int, int]:
        return (sum(a.reply.usage.tokens_in for a in self.attempts),
                sum(a.reply.usage.tokens_out for a in self.attempts))


def _schema_fail(msg: str) -> LadderOutcome:
    out = LadderOutcome()
    out.results.append(RungResult(rung=Rung.SCHEMA, passed=False, summary="design did not validate", detail=msg))
    return out


def _format_validation_error(e: ValidationError) -> str:
    lines = []
    for err in e.errors()[:8]:
        loc = ".".join(str(x) for x in err.get("loc", []))
        lines.append(f"{loc}: {err.get('msg')}")
    return "\n".join(lines)


def run_generation(
    request: str,
    provider: Provider,
    cat: Catalogue,
    workdir: Path,
    *,
    board: str = "wokwi-esp32-devkit-v1",
    max_attempts: int = 3,
    simulate: bool = False,
    scenario: Path | None = None,
    timeout_ms: int = 5000,
    grounded: bool = True,
    use_feedback: bool = True,
    inject_serial_monitor: bool = False,
    on_event=None,
    scenario_factory=None,
) -> RunResult:
    """Run the loop. ``on_event(kind, payload)`` receives progress for a CLI or UI.

    ``scenario_factory(design, attempt_dir) -> Path`` builds a scenario for a design
    when no fixed task scenario exists (free-form prompts from the web app).
    """
    emit = on_event or (lambda kind, payload: None)
    result = RunResult(request=request)
    workdir.mkdir(parents=True, exist_ok=True)

    prev_wire: dict | None = None
    prev_feedback = ""

    for n in range(1, max_attempts + 1):
        t0 = time.time()
        if n == 1 or not use_feedback:
            user = build_user_prompt(request, cat, board=board, grounded=grounded)
        else:
            user = build_retry_prompt(request, cat, board=board, previous_wire=prev_wire or {},
                                      feedback=prev_feedback, attempt=n, max_attempts=max_attempts,
                                      grounded=grounded)
        emit("model.start", {"attempt": n})
        reply = provider.generate(SYSTEM, user)
        emit("model.done", {"attempt": n, "tokens_in": reply.usage.tokens_in,
                            "tokens_out": reply.usage.tokens_out, "latency_s": reply.usage.latency_s})

        adir = workdir / f"attempt_{n}"
        adir.mkdir(parents=True, exist_ok=True)
        (adir / "reply.json").write_text(reply.raw)

        design: Design | None = None
        try:
            design = Design.model_validate(to_design_dict(reply.wire))
        except (ValidationError, TypeError, AttributeError) as e:
            msg = _format_validation_error(e) if isinstance(e, ValidationError) else str(e)
            outcome = _schema_fail(msg)
        else:
            (adir / "ir.json").write_text(design.model_dump_json(indent=2))
            scen = scenario
            if simulate and scen is None and scenario_factory is not None:
                scen = scenario_factory(design, adir)
            outcome = run_ladder(design, cat, adir, scenario=scen, timeout_ms=timeout_ms,
                                 simulate=simulate, inject_serial_monitor=inject_serial_monitor,
                                 on_rung=lambda r: emit("rung", {"attempt": n, "rung": r.rung.value,
                                                                  "passed": r.passed, "summary": r.summary,
                                                                  "seconds": r.seconds}))

        feedback = outcome.feedback()
        att = Attempt(n=n, reply=reply, design=design, outcome=outcome, feedback=feedback,
                      seconds=time.time() - t0)
        result.attempts.append(att)
        (adir / "feedback.txt").write_text(feedback)
        emit("attempt.done", {"attempt": n, "passed": att.passed, "failed_rung": att.failed_rung})

        if att.passed:
            break
        prev_wire = reply.wire
        prev_feedback = feedback

    (workdir / "summary.json").write_text(json.dumps({
        "request": request,
        "passed": result.passed,
        "attempts": [{"n": a.n, "passed": a.passed, "failed_rung": a.failed_rung,
                      "tokens_in": a.reply.usage.tokens_in, "tokens_out": a.reply.usage.tokens_out,
                      "seconds": round(a.seconds, 1)} for a in result.attempts],
        "model": result.attempts[0].reply.model if result.attempts else "",
        "catalogue": cat.hash,
    }, indent=2))
    return result
