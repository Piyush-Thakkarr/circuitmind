"""Turn a verified Design into a build guide a beginner can follow."""

from __future__ import annotations

from .catalogue import Catalogue
from .ir import BOARD_ID, Design

# Approximate Indian hobby-retailer prices in rupees. Rough, for budgeting only.
PRICES: dict[str, tuple[str, int]] = {
    "wokwi-esp32-devkit-v1": ("ESP32 DevKit v1", 450),
    "wokwi-led": ("5 mm LED", 5),
    "wokwi-rgb-led": ("RGB LED, common cathode", 15),
    "wokwi-resistor": ("Resistor", 1),
    "wokwi-pushbutton": ("Tactile pushbutton", 5),
    "wokwi-slide-switch": ("Slide switch", 10),
    "wokwi-potentiometer": ("10k potentiometer", 25),
    "wokwi-buzzer": ("Piezo buzzer", 20),
    "wokwi-servo": ("SG90 servo", 150),
    "wokwi-dht22": ("DHT22 sensor", 250),
    "wokwi-hc-sr04": ("HC-SR04 ultrasonic", 90),
    "wokwi-photoresistor-sensor": ("LDR module", 40),
    "wokwi-ntc-temperature-sensor": ("NTC thermistor module", 40),
    "wokwi-pir-motion-sensor": ("PIR motion sensor", 80),
    "wokwi-mpu6050": ("MPU6050 IMU", 150),
    "wokwi-ds18b20": ("DS18B20 temperature probe", 90),
    "wokwi-lcd1602": ("16x2 LCD with I2C", 180),
    "wokwi-lcd2004": ("20x4 LCD with I2C", 300),
    "board-ssd1306": ("0.96 in OLED", 220),
    "wokwi-7segment": ("7-segment display", 30),
    "wokwi-neopixel": ("WS2812 NeoPixel", 15),
    "wokwi-membrane-keypad": ("4x4 keypad", 60),
    "wokwi-ky-040": ("KY-040 rotary encoder", 50),
    "wokwi-relay-module": ("Relay module", 60),
    "wokwi-stepper-motor": ("28BYJ-48 stepper", 120),
    "wokwi-ir-receiver": ("IR receiver", 25),
}

_PIN_WORDS = {
    "A": "anode, the longer leg", "C": "cathode, the shorter leg", "COM": "common pin",
    "VCC": "power in", "VDD": "power in", "V+": "power in", "GND": "ground", "VSS": "ground",
    "PWM": "signal", "SIG": "signal", "OUT": "output", "DQ": "data", "SDA": "SDA data", "SCL": "SCL clock",
    "TRIG": "trigger", "ECHO": "echo", "DIN": "data in", "DOUT": "data out",
}


def _pin_words(part_type: str, pin: str) -> str:
    base = pin.split(".")[0]
    if base in _PIN_WORDS:
        return f"{pin} ({_PIN_WORDS[base]})"
    return pin


def _board_pin_words(pin: str) -> str:
    if pin.startswith("GND"):
        return f"{pin} (any ground pin)"
    if pin in ("3V3",):
        return "3V3 (3.3 volt supply)"
    if pin in ("VIN",):
        return "VIN (5 volt supply from USB)"
    if pin.startswith("D") and pin[1:].isdigit():
        return f"{pin} (GPIO {pin[1:]})"
    return pin


def build_guide(design: Design, cat: Catalogue, *, verified: bool = True) -> dict:
    types = {p.id: p.type for p in design.parts}
    types[BOARD_ID] = design.board
    labels = {p.id: (PRICES.get(p.type, (p.type, 0))[0]) for p in design.parts}
    labels[BOARD_ID] = PRICES.get(design.board, (design.board, 0))[0]

    def name(pid: str) -> str:
        if pid == BOARD_ID:
            return "the ESP32"
        p = next(x for x in design.parts if x.id == pid)
        extra = ""
        if p.type == "wokwi-resistor" and "value" in p.attrs:
            extra = f" ({p.attrs['value']} ohm)"
        elif p.type == "wokwi-led" and "color" in p.attrs:
            extra = f" ({p.attrs['color']})"
        return f"{labels[pid]} {pid}{extra}"

    # Order wiring: power and ground last, so signal connections read first.
    def is_power(conn):
        a, b = conn
        pins = {a.split(":")[1].split(".")[0], b.split(":")[1].split(".")[0]}
        return bool(pins & {"GND", "VSS", "VCC", "VDD", "V+", "3V3", "VIN", "5V"})

    ordered = sorted(design.connections, key=is_power)
    steps = []
    for a, b in ordered:
        pa, pina = a.split(":", 1)
        pb, pinb = b.split(":", 1)
        left = f"{name(pa)} pin {_board_pin_words(pina) if pa == BOARD_ID else _pin_words(types[pa], pina)}"
        right = f"{name(pb)} pin {_board_pin_words(pinb) if pb == BOARD_ID else _pin_words(types[pb], pinb)}"
        steps.append(f"Connect {left} to {right}.")

    # Parts list with quantities.
    counts: dict[tuple[str, str], int] = {}
    for p in design.parts:
        key = (p.type, p.attrs.get("value", "") if p.type == "wokwi-resistor" else "")
        counts[key] = counts.get(key, 0) + 1
    parts = [{"name": PRICES.get(design.board, (design.board, 0))[0], "qty": 1,
              "approx_inr": PRICES.get(design.board, ("", 0))[1]}]
    for (t, val), n in counts.items():
        label, price = PRICES.get(t, (t, 0))
        if t == "wokwi-resistor" and val:
            label = f"Resistor {val} ohm"
        parts.append({"name": label, "qty": n, "approx_inr": price * n})
    parts.append({"name": "Breadboard and jumper wires", "qty": 1, "approx_inr": 150})
    total = sum(p["approx_inr"] for p in parts)

    notes = []
    if any(p.type in ("wokwi-led", "wokwi-rgb-led") for p in design.parts):
        notes.append("LEDs only light one way round. The longer leg is the anode (A).")
    if any(p.type == "wokwi-servo" for p in design.parts):
        notes.append("Power the servo from VIN (5 V), not 3V3. A 3.3 V supply will stall it.")
    if any(p.type == "wokwi-pushbutton" for p in design.parts):
        notes.append("The button uses the ESP32's internal pull-up, so it reads LOW when pressed.")
    if verified:
        notes.append("This design passed logic and wiring checks in simulation. Current draw and power limits are not simulated; double-check anything that moves or heats.")
    else:
        notes.append("This design did NOT pass verification. It is shown so you can see what was tried; do not build it as is.")

    return {
        "summary": design.explanation or "",
        "status_line": design.status_line,
        "wiring": steps,
        "parts": parts,
        "total_inr": total,
        "notes": notes,
        "firmware": design.firmware,
    }
