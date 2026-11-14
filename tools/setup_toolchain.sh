#!/usr/bin/env sh
# Installs arduino-cli with the ESP32 core and the libraries the task suite uses, plus wokwi-cli.
set -e
if ! command -v arduino-cli >/dev/null 2>&1; then
  curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR="$HOME/.local/bin" sh
  export PATH="$HOME/.local/bin:$PATH"
fi
arduino-cli config init --overwrite >/dev/null 2>&1 || true
arduino-cli config add board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json >/dev/null 2>&1 || true
arduino-cli core update-index
arduino-cli core install esp32:esp32
arduino-cli lib install "ESP32Servo" "DHT sensor library" "Adafruit Unified Sensor" "LiquidCrystal I2C" "Stepper" "OneWire" "DallasTemperature" "MPU6050" "Adafruit MPU6050" "Adafruit BusIO"
# esptool from pip starts in under a second; the one the ESP32 core ships unpacks itself on every run (about 6 s each, three runs per compile)
python3 -m pip install -q "esptool==5.3.1" || echo "pip esptool not installed; compiles will be slower"
if ! command -v wokwi-cli >/dev/null 2>&1; then
  curl -fsSL https://wokwi.com/ci/install.sh | sh
fi
echo "toolchain ready. add \$HOME/.local/bin and \$HOME/.wokwi/bin to PATH if not already."
