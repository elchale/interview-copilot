"""Publisher that batches live events and POSTs them to the web app's /api/ingest.

Implements the same interface as src.server (and BrowserPublisher), so it can drive
LiveSession directly. Events are buffered and flushed on a short interval to keep
DB writes cheap while staying near real time.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)


class RemotePublisher:
    """Buffers LiveSession events and uploads them to the cloud viewer in batches."""

    def __init__(self, ingest_url: str, token: str) -> None:
        self._url = ingest_url
        self._token = token
        self._buf: list[dict[str, Any]] = []

    def _emit(self, kind: str, payload: dict[str, Any]) -> None:
        self._buf.append({"kind": kind, "payload": payload})

    # --- publisher API consumed by LiveSession ---
    def update_status(self, **kwargs: Any) -> None:
        self._emit("status", kwargs)

    def add_transcript(self, text: str, source: str = "system") -> None:
        self._emit("transcript", {"text": text, "source": source})

    def start_answer(self, answer_id: str) -> None:
        self._emit("answer.start", {"answerId": answer_id})

    def stream_answer_delta(self, answer_id: str, delta: str) -> None:
        self._emit("answer.delta", {"answerId": answer_id, "text": delta})

    def finish_answer(self, answer_id: str, latency_ms: int | None = None) -> None:
        self._emit("answer.done", {"answerId": answer_id, "latencyMs": latency_ms})

    def error_answer(self, answer_id: str, error: str = "") -> None:
        self._emit("answer.error", {"answerId": answer_id, "error": error})

    # --- background flusher ---
    async def run_flusher(self, interval: float = 0.4) -> None:
        async with httpx.AsyncClient(timeout=10.0) as client:
            while True:
                await asyncio.sleep(interval)
                await self._flush(client)

    async def flush_now(self) -> None:
        """Send any buffered events immediately (used on stop so the web sees it)."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            await self._flush(client)

    async def _flush(self, client: httpx.AsyncClient) -> None:
        if not self._buf:
            return
        batch, self._buf = self._buf, []
        try:
            await client.post(
                self._url,
                json={"events": batch},
                headers={"Authorization": f"Bearer {self._token}"},
            )
        except Exception as e:
            logger.warning("ingest flush failed (%s); re-queuing %d events", e, len(batch))
            self._buf[0:0] = batch  # retry next tick
