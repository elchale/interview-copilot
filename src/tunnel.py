"""Optional cloudflared tunnel for public URL access."""

from __future__ import annotations

import logging
import re
import shutil
import subprocess
import threading

logger = logging.getLogger(__name__)


class Tunnel:
    """Manage a cloudflared quick tunnel to expose the local server."""

    def __init__(self, port: int = 7123) -> None:
        self._port = port
        self._process: subprocess.Popen | None = None
        self._url: str | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str | None:
        return self._url

    @property
    def is_running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self) -> str | None:
        """Start a cloudflared tunnel. Returns the public URL or None on failure."""
        binary = shutil.which("cloudflared")
        if not binary:
            logger.error(
                "cloudflared not found. Install it: "
                "https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"
            )
            return None

        try:
            self._process = subprocess.Popen(
                [binary, "tunnel", "--url", f"http://127.0.0.1:{self._port}"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )

            self._thread = threading.Thread(target=self._read_output, daemon=True)
            self._thread.start()

            # Wait up to 15s for the URL to appear
            for _ in range(150):
                if self._url:
                    logger.info("Tunnel URL: %s", self._url)
                    return self._url
                import time
                time.sleep(0.1)

            logger.warning("Tunnel started but URL not captured within 15s")
            return None

        except Exception as e:
            logger.error("Failed to start tunnel: %s", e)
            return None

    def stop(self) -> None:
        if self._process:
            self._process.terminate()
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()
            self._process = None
            self._url = None
            logger.info("Tunnel stopped")

    def _read_output(self) -> None:
        if not self._process or not self._process.stdout:
            return
        url_pattern = re.compile(r"(https://[a-z0-9-]+\.trycloudflare\.com)")
        for line in self._process.stdout:
            match = url_pattern.search(line)
            if match:
                self._url = match.group(1)
