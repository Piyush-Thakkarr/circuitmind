# The engine as a container, for any Docker host that can run it.
# It is not deployed anywhere yet: Hugging Face Docker Spaces need a paid plan
# since 2026 and the project spends nothing. See docs/roadmap.md section 2.
# Runs as user 1000 (what most hosts expect), listens on $PORT (default 7860).
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:/home/user/.wokwi/bin:/home/user/bin:$PATH

# arduino-cli with the ESP32 core and the libraries the tasks use
RUN mkdir -p /home/user/bin \
    && curl -fsSL https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh | BINDIR=/home/user/bin sh \
    && arduino-cli config init \
    && arduino-cli config add board_manager.additional_urls https://espressif.github.io/arduino-esp32/package_esp32_index.json \
    && arduino-cli core update-index \
    && arduino-cli core install esp32:esp32 \
    && arduino-cli lib install "ESP32Servo" "DHT sensor library" "Adafruit Unified Sensor" "LiquidCrystal I2C" "Stepper" "OneWire" "DallasTemperature" "MPU6050" "Adafruit MPU6050" "Adafruit BusIO"

# wokwi-cli
RUN curl -fsSL https://wokwi.com/ci/install.sh | sh

WORKDIR /home/user/app
COPY --chown=user pyproject.toml ./
COPY --chown=user src ./src
COPY --chown=user catalogue ./catalogue
COPY --chown=user benchmark ./benchmark
COPY --chown=user tools ./tools
RUN pip install --no-cache-dir --user -e . "esptool==5.3.1"

# Warm the build cache with a trivial ESP32 compile so the first real one is fast
RUN mkdir -p /tmp/warm/warm && printf 'void setup(){} void loop(){}' > /tmp/warm/warm/warm.ino \
    && arduino-cli compile --fqbn esp32:esp32:esp32doit-devkit-v1 /tmp/warm/warm >/dev/null \
    && rm -rf /tmp/warm

ENV PORT=7860
EXPOSE 7860
CMD ["sh", "-c", "circuitmind serve --host 0.0.0.0 --port ${PORT}"]
