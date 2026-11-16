#!/bin/sh
# Container entry point: serve at once, and warm the arduino-cli cache in the
# background by compiling T01's reference once, so the first real compile on a
# fresh host (or after a restart that lost /tmp) is as fast as the ones after it.
set -e
PORT="${PORT:-7860}"
( circuitmind warm T01_blink || echo "warm compile failed; the first real compile will be slow" ) &
exec circuitmind serve --host 0.0.0.0 --port "$PORT"
