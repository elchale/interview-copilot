"""Local capture agent for the Vercel-viewer architecture.

The agent runs the FULL pipeline locally (capture + STT + LLM) using the user's
own keys (DPAPI, never uploaded) and publishes the resulting transcript/answer
events to the web app, which the browser polls. On first run it pairs with the
site via the browser (Google login), then streams events.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import webbrowser
from pathlib import Path

import httpx

from src.live_session import LiveSession
from src.recorder import Recorder
from src.settings import DATA_DIR, Settings
from .remote_publisher import RemotePublisher

logger = logging.getLogger(__name__)

BASE_URL = os.environ.get("CLOUD_BASE_URL", "https://bebita.club").rstrip("/")
TOKEN_PATH = Path(DATA_DIR) / "agent.json"


def _load() -> dict:
    try:
        return json.loads(TOKEN_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save(data: dict) -> None:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_PATH.write_text(json.dumps(data), encoding="utf-8")


async def pair() -> tuple[str, str]:
    """Browser pairing flow. Returns (token, ingest_url)."""
    async with httpx.AsyncClient(timeout=20.0) as client:
        start = (await client.post(f"{BASE_URL}/api/pair/start")).json()
        print(f"\nOpening your browser to sign in:\n  {start['verify_url']}\n")
        webbrowser.open(start["verify_url"])
        for _ in range(150):  # ~5 min
            await asyncio.sleep(2)
            r = await client.get(start["poll_url"])
            if r.status_code == 404:
                raise RuntimeError("Pairing code expired — restart the app.")
            data = r.json()
            if data.get("status") == "claimed":
                token, ingest = data["token"], data["ingest_url"]
                _save({"token": token, "ingest_url": ingest})
                return token, ingest
        raise RuntimeError("Pairing timed out — restart the app.")


async def run() -> None:
    saved = _load()
    token, ingest_url = saved.get("token", ""), saved.get("ingest_url", "")
    if not token or not ingest_url:
        token, ingest_url = await pair()

    settings = Settings.load()  # local, DPAPI-encrypted keys — never leave the machine
    loop = asyncio.get_running_loop()
    publisher = RemotePublisher(ingest_url, token)
    live = LiveSession(settings, loop, publisher=publisher)

    recorder = Recorder(
        loopback_device_index=settings.loopback_device_index,
        on_system_audio=live.feed_audio,
    )
    recorder.start()
    await live.start()
    flusher = asyncio.create_task(publisher.run_flusher())

    print("Live. Open your feed at:", f"{BASE_URL}/feed")
    webbrowser.open(f"{BASE_URL}/feed")
    try:
        await asyncio.Event().wait()  # run until interrupted
    finally:
        flusher.cancel()
        await live.stop()
        recorder.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
