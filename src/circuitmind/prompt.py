"""Prompt construction for generation and for retries."""

from __future__ import annotations

import json

from .catalogue import Catalogue

SYSTEM = """You design small ESP32 electronics projects and write the Arduino firmware for them.

You output one JSON object describing the whole design: the board, the parts, the wire connections, the firmware, and a status line.

Rules you must follow:
- Use only part types from the catalogue you are given. Never invent a part type.
- Use only pin names listed for each part. The board's id is always "esp". Reference pins as "partid:PIN", for example "led1:A" or "esp:D2".
- Give every part a short lowercase id (led1, r1, btn1, servo1). Never reuse an id. Never use "esp" as a part id.
- Every LED needs a series resistor (wokwi-resistor, value "220").
- On this board, D34, D35, VN and VP are input-only. Do not drive outputs on them.
- Firmware is a complete Arduino sketch with setup() and loop(). Call Serial.begin(115200) in setup().
- The firmware must print the status_line to Serial, exactly, once the requested behaviour has been demonstrated. Keep the status line short and uppercase, for example BLINK or PRESSED. For a reading, make the status line the fixed prefix only, for example DIST=, and print the value after it.
- GPIO numbers in the firmware must match the board pins you wired. Pin D2 is GPIO 2, D4 is GPIO 4, and so on.
- Prefer libraries available in the Arduino Library Manager. For servos on ESP32 use the ESP32Servo library.
- Keep the design as simple as the request allows. No extra parts.
- attrs is a list of key/value pairs, for example [{"key":"color","value":"red"}] for an LED or [{"key":"value","value":"220"}] for a resistor.
"""


def build_user_prompt(request: str, cat: Catalogue, *, board: str, grounded: bool = True) -> str:
    parts = [f"Board: {board}", "", f"Request: {request.strip()}", ""]
    if grounded:
        parts += [
            "Catalogue of allowed part types and their pins:",
            cat.prompt_block(),
            "",
        ]
    parts += ["Return the design as one JSON object matching the schema."]
    return "\n".join(parts)


def build_retry_prompt(request: str, cat: Catalogue, *, board: str, previous_wire: dict, feedback: str,
                       attempt: int, max_attempts: int, grounded: bool = True) -> str:
    base = build_user_prompt(request, cat, board=board, grounded=grounded)
    return "\n".join([
        base,
        "",
        f"This is attempt {attempt} of {max_attempts}. Your previous design failed verification.",
        "",
        "Previous design:",
        json.dumps(previous_wire, indent=2),
        "",
        "Verification result:",
        feedback.strip(),
        "",
        "Fix the problem described above. Keep everything that was already correct. Return the full corrected design.",
    ])
