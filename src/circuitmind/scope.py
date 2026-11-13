"""Catch requests that cannot be built from the catalogue before any model call.

The catalogue is a few dozen hobby parts on one ESP32. Drones, mains power,
walking robots, cameras and radios are not in it and the simulator cannot
check them. A keyword screen gives a clear answer at once and names the
closest thing that can be built. The model also carries a rule for the cases
the keywords miss (see prompt.SYSTEM).
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Refusal:
    topic: str
    reason: str
    closest: str


_RULES: list[tuple[re.Pattern[str], Refusal]] = [
    (re.compile(r"\b(drone|quadcopter|quad-?copter|fly|flies|flying|aircraft|airplane|plane|propellers?)\b", re.IGNORECASE),
     Refusal("flying things",
             "A drone needs brushless motors, speed controllers and a flight controller. None of those are in the "
             "catalogue, and the simulator cannot model flight.",
             "a servo that moves when a button is pressed, or an MPU6050 tilt alarm that lights an LED")),
    (re.compile(r"\b(mains|230\s?v|240\s?v|110\s?v|120\s?v|ac\s+power|wall\s+(socket|outlet|plug)|high\s+voltage)\b",
                re.IGNORECASE),
     Refusal("mains power",
             "Mains voltage is dangerous and nothing here can check it: the simulator has no mains, and the catalogue "
             "has only low-voltage parts.",
             "a relay module driven by the ESP32 with an LED standing in for the lamp, so the switching logic is "
             "verified and the mains side is left to a qualified person")),
    (re.compile(r"\b(walk(s|ing)?|legs?|legged|humanoid|biped|quadruped|robot\s+arm|robotic\s+arm)\b", re.IGNORECASE),
     Refusal("walking robots and arms",
             "A walking robot or an arm needs several servos, a frame and motion control. The catalogue has one hobby "
             "servo and no mechanics, and the simulator moves one servo at a time.",
             "a single servo swept by a potentiometer or a joystick")),
    (re.compile(r"\b(dc\s+motors?|wheels?|rover|car|vehicle|motor\s+driver|l298n?|h-?bridge|tracks?)\b", re.IGNORECASE),
     Refusal("wheeled vehicles and DC motors",
             "There is no DC motor and no motor driver in the catalogue, so a vehicle cannot be wired or simulated.",
             "a stepper motor turning a set number of steps, or a servo")),
    (re.compile(r"\b(camera|esp32-?cam|video|photo|image|stream(s|ing)?|face|object\s+detection)\b", re.IGNORECASE),
     Refusal("cameras and vision",
             "No camera module is in the catalogue and the simulator has no picture to look at.",
             "a PIR motion sensor that lights an LED and prints MOTION, or an LDR that reports light level")),
    (re.compile(r"\b(gps|gsm|sim\s+card|cellular|lora|lorawan|4g|5g|satellite)\b", re.IGNORECASE),
     Refusal("radios and positioning",
             "GPS, cellular and LoRa modules are not in the catalogue and the simulator has no radio environment.",
             "the sensor side of the project, printing its readings to the serial monitor")),
    (re.compile(r"\b(wi-?fi|bluetooth|ble|internet|cloud|mqtt|http|web\s*server|website|phone\s+app|telegram|alexa)\b",
                re.IGNORECASE),
     Refusal("wireless and internet features",
             "Network features are not checked by this tool: the scenario only presses buttons and watches pins and "
             "serial output.",
             "the physical part on its own: what should light up, move or print, and when")),
    (re.compile(r"\b(speaker|mp3|wav|music\s+file|audio\s+play|microphone|mic|voice|speech|talk(s|ing)?)\b",
                re.IGNORECASE),
     Refusal("sound playback and voice",
             "There is no speaker, amplifier or microphone in the catalogue; the only sound part is a piezo buzzer.",
             "a buzzer that beeps a pattern, which the simulator can check")),
]


def screen(prompt: str) -> Refusal | None:
    """Return a Refusal when the prompt clearly asks for something outside the catalogue, else None."""
    for pattern, refusal in _RULES:
        if pattern.search(prompt):
            return refusal
    return None


def message(r: Refusal) -> str:
    return f"This asks for {r.topic}, which CircuitMind cannot build or check. {r.reason} Closest thing it can do: {r.closest}."
