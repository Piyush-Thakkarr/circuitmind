"""The out-of-scope screen: five prompts it must catch, and the task prompts it must not."""

from pathlib import Path

import yaml

from circuitmind.prompt import SYSTEM
from circuitmind.scope import message, screen

TASKS = Path(__file__).resolve().parents[1] / "benchmark" / "tasks"

OUT_OF_SCOPE = {
    "A drone that follows me around the room": "flying things",
    "Switch a 230V lamp on and off from the ESP32": "mains power",
    "A robot that walks on four legs and avoids obstacles": "walking robots and arms",
    "A small car with two DC motors and wheels controlled by a joystick": "wheeled vehicles and DC motors",
    "An ESP32 camera that streams video to my phone": "cameras and vision",
}


def test_five_out_of_scope_prompts_are_caught():
    for prompt, topic in OUT_OF_SCOPE.items():
        r = screen(prompt)
        assert r is not None, prompt
        assert r.topic == topic
        text = message(r)
        assert "cannot build or check" in text and "Closest thing" in text


def test_no_benchmark_prompt_is_screened():
    for f in sorted(TASKS.glob("*/task.yaml")):
        prompt = yaml.safe_load(f.read_text())["prompt"]
        assert screen(prompt) is None, f.parent.name


def test_relay_with_led_stand_in_is_in_scope():
    assert screen("A relay module that clicks on when a button is pressed, with an LED showing its state") is None
    assert screen("A buzzer that plays three beeps") is None


def test_system_prompt_carries_the_closest_buildable_rule():
    assert "closest" in SYSTEM.lower() and "left out" in SYSTEM.lower()
