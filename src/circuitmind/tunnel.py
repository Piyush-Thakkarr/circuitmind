"""Put the local engine on a public https address with a Cloudflare quick tunnel.

Hosting the engine around the clock is not free any more (Hugging Face Docker
Spaces need a paid plan since 2026, and every other host that can run the
ESP32 toolchain wants a card). So the engine runs on the owner's machine and
``circuitmind serve --tunnel`` opens a quick tunnel with ``cloudflared``, which
needs no account. The address changes on every start, so the command prints a
ready-to-share link to the web app that carries the engine address in the URL.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import threading
import time

WEB_URL = os.environ.get("CIRCUITMIND_WEB_URL", "https://circuit-mind-landing.vercel.app")
_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")
_START_TIMEOUT_S = 30


def tunnel_url_from_log(text: str) -> str | None:
    """The public address cloudflared printed, if it is in ``text``."""
    m = _URL_RE.search(text)
    return m.group(0) if m else None


def share_link(engine_url: str) -> str:
    """The web app address that opens already pointed at this engine."""
    return f"{WEB_URL}/app.html?engine={engine_url}"


class QuickTunnel:
    """A running ``cloudflared tunnel --url`` process. Use ``start`` then ``stop``."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.url: str | None = None
        self._proc: subprocess.Popen | None = None
        self._log: list[str] = []

    def start(self) -> str:
        if shutil.which("cloudflared") is None:
            raise RuntimeError(
                "cloudflared is not installed. On a Mac: brew install cloudflared. "
                "Then run the command again."
            )
        self._proc = subprocess.Popen(
            ["cloudflared", "tunnel", "--url", f"http://127.0.0.1:{self.port}", "--no-autoupdate"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        threading.Thread(target=self._pump, daemon=True).start()
        deadline = time.time() + _START_TIMEOUT_S
        while time.time() < deadline:
            if self.url:
                return self.url
            if self._proc.poll() is not None:
                break
            time.sleep(0.2)
        self.stop()
        tail = "".join(self._log[-5:]).strip()
        raise RuntimeError(f"cloudflared did not give a tunnel address in {_START_TIMEOUT_S} s. {tail}")

    def _pump(self) -> None:
        assert self._proc and self._proc.stdout
        for line in self._proc.stdout:
            self._log.append(line)
            if self.url is None:
                self.url = tunnel_url_from_log(line)

    def stop(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
