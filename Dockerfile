# The engine as a container. Built on a laptop for linux/amd64 and loaded on the
# Oracle Always Free VM (see docs/deploy.md); nothing is built on the VM.
# Runs as user 1000, listens on $PORT (default 7860). The arduino-cli cache at
# /home/user/.cache/arduino is meant to be a volume so warm compiles survive restarts.
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

COPY --chown=user tools/engine_start.sh /home/user/bin/engine_start.sh

# One compile job: the target host has one shared CPU and 1 GB of memory.
ENV CIRCUITMIND_COMPILE_JOBS=1
ENV PORT=7860
EXPOSE 7860
CMD ["/home/user/bin/engine_start.sh"]
