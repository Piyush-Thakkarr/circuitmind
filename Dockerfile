FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

# arduino-cli with the ESP32 core, warmed so the first user compile is fast
RUN curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR=/usr/local/bin sh \
    && arduino-cli config init \
    && arduino-cli config add board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json \
    && arduino-cli core update-index \
    && arduino-cli core install esp32:esp32 \
    && arduino-cli lib install "ESP32Servo" "DHT sensor library" "Adafruit Unified Sensor" "LiquidCrystal I2C"

# wokwi-cli
RUN curl -fsSL https://wokwi.com/ci/install.sh | sh
ENV PATH="/root/.wokwi/bin:${PATH}"

WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
COPY catalogue ./catalogue
COPY benchmark ./benchmark
COPY tools ./tools
RUN pip install --no-cache-dir -e .

# Warm the build cache with a trivial ESP32 compile
RUN mkdir -p /tmp/warm/warm && printf 'void setup(){} void loop(){}' > /tmp/warm/warm/warm.ino \
    && arduino-cli compile --fqbn esp32:esp32:esp32doit-devkit-v1 /tmp/warm/warm >/dev/null \
    && rm -rf /tmp/warm

ENTRYPOINT ["circuitmind"]
CMD ["--help"]
