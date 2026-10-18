"""Extract the part catalogue from wokwi-cli lint.

For each candidate part type, lint a diagram that wires a bogus pin. Lint
rejects it and prints the valid pin list. That list is what the simulator
actually accepts, so it is the authoritative source.

Usage:
    python tools/extract_catalogue.py > catalogue/parts.json
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

CANDIDATES: dict[str, str] = {
    # type: one-line description for the model
    "wokwi-esp32-devkit-v1": "ESP32 DevKit v1 board. GPIO pins are named D<n>. D34, D35, VN, VP are input-only.",
    "wokwi-led": "Single-colour LED. attrs.color: red, green, blue, yellow, white, orange.",
    "wokwi-rgb-led": "Common-cathode RGB LED. COM to ground, R/G/B through resistors.",
    "wokwi-resistor": "Resistor. attrs.value in ohms as a string, e.g. \"220\".",
    "wokwi-pushbutton": "Momentary pushbutton. Pins 1.l/1.r are one side, 2.l/2.r the other. attrs.color optional.",
    "wokwi-slide-switch": "SPDT slide switch. Pin 2 is common; 1 and 3 are the two positions.",
    "wokwi-potentiometer": "Rotary potentiometer. SIG to an ADC-capable pin.",
    "wokwi-buzzer": "Piezo buzzer. Pin 1 to GPIO, pin 2 to ground.",
    "wokwi-servo": "Hobby servo. PWM to a GPIO, V+ to 5V or VIN, GND to ground.",
    "wokwi-dht22": "DHT22 temperature and humidity sensor. SDA is the data pin. Use the DHT sensor library.",
    "wokwi-hc-sr04": "HC-SR04 ultrasonic distance sensor. TRIG output, ECHO input.",
    "wokwi-photoresistor-sensor": "LDR module with analog (AO) and digital (DO) outputs.",
    "wokwi-ntc-temperature-sensor": "NTC thermistor module with analog OUT.",
    "wokwi-pir-motion-sensor": "PIR motion sensor. OUT goes high on motion.",
    "wokwi-mpu6050": "MPU6050 6-axis IMU over I2C (SDA, SCL). Address 0x68.",
    "wokwi-ds18b20": "DS18B20 one-wire temperature sensor. DQ is the data pin, needs a pull-up.",
    "wokwi-lcd1602": "16x2 character LCD. Use SCL/SDA for the I2C backpack (LiquidCrystal_I2C, address 0x27).",
    "wokwi-lcd2004": "20x4 character LCD. Use SCL/SDA for the I2C backpack (address 0x27).",
    "board-ssd1306": "128x64 OLED over I2C (Adafruit_SSD1306, address 0x3C).",
    "wokwi-7segment": "Seven-segment display. attrs.digits sets number of digits.",
    "wokwi-neopixel": "Single WS2812 NeoPixel. DIN from GPIO, DOUT to the next pixel.",
    "wokwi-membrane-keypad": "4x4 membrane keypad. Rows R1-R4, columns C1-C4. Use the Keypad library.",
    "wokwi-ky-040": "KY-040 rotary encoder. CLK, DT for rotation, SW for the push.",
    "wokwi-relay-module": "Relay module. IN from GPIO; NO/NC/COM are the switched contacts.",
    "wokwi-stepper-motor": "Bipolar stepper. Needs a driver; A+/A-/B+/B- are coil ends.",
    "wokwi-ir-receiver": "IR receiver. DAT to GPIO. Use IRremote.",
    "wokwi-analog-joystick": "Two-axis joystick with push. VERT/HORZ analog, SEL digital.",
    "wokwi-microsd-card": "MicroSD over SPI. CS, SCK, DI (MOSI), DO (MISO).",
    "wokwi-ili9341": "ILI9341 TFT over SPI.",
}

_PINS_RE = re.compile(r"Valid pins: ([^(]+)\(")


def probe(part_type: str) -> list[str] | None:
    with tempfile.TemporaryDirectory() as td:
        diagram = {
            "version": 1,
            "author": "probe",
            "editor": "wokwi",
            "parts": [
                {"type": "wokwi-esp32-devkit-v1", "id": "esp", "attrs": {}},
                {"type": part_type, "id": "p", "attrs": {}},
            ],
            "connections": [["p:ZZZZ", "esp:GND.1", "black", []]],
        }
        Path(td, "diagram.json").write_text(json.dumps(diagram))
        r = subprocess.run(
            ["wokwi-cli", "lint", td], capture_output=True, text=True, timeout=60
        )
        out = r.stdout + r.stderr  # findings go to stderr, summary to stdout
    if "unknown-part-type" in out:
        return None
    m = _PINS_RE.search(out)
    if not m:
        return None
    return [p.strip() for p in m.group(1).split(",") if p.strip()]


def main() -> int:
    parts: dict[str, dict] = {}
    for t, desc in CANDIDATES.items():
        pins = probe(t)
        if pins is None:
            print(f"skip {t}: not accepted by lint", file=sys.stderr)
            continue
        parts[t] = {"pins": pins, "description": desc}
        print(f"ok   {t}: {len(pins)} pins", file=sys.stderr)

    body = json.dumps(parts, sort_keys=True, indent=2)
    snapshot = {
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "wokwi-cli lint",
        "hash": hashlib.sha256(body.encode()).hexdigest()[:16],
        "parts": parts,
    }
    print(json.dumps(snapshot, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
