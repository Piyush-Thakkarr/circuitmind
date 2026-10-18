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
arduino-cli lib install "ESP32Servo" "DHT sensor library" "Adafruit Unified Sensor" "LiquidCrystal I2C"
if ! command -v wokwi-cli >/dev/null 2>&1; then
  curl -fsSL https://wokwi.com/ci/install.sh | sh
fi
echo "toolchain ready. add \$HOME/.local/bin and \$HOME/.wokwi/bin to PATH if not already."
