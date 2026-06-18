"""Deepgram streaming STT over WebSocket — used by live call mode.

Unlike the batch ``DeepgramProvider``, this keeps a socket open and yields
finalized utterances in real time, using Deepgram's endpointing and
``UtteranceEnd`` events for "smart chunk breaking" (detecting when a speaker
starts and stops talking).
"""

from __future__ import annotations

import json
import logging
from typing import AsyncIterator
from urllib.parse import urlencode

import websockets

logger = logging.getLogger(__name__)

DEEPGRAM_WS_URL = "wss://api.deepgram.com/v1/listen"


class DeepgramStream:
    """A live Deepgram transcription socket fed raw 16-bit PCM audio."""

    def __init__(self, api_key: str, model: str = "nova-3", sample_rate: int = 16000) -> None:
        self._api_key = api_key
        self._model = model
        self._sample_rate = sample_rate
        self._ws: websockets.WebSocketClientProtocol | None = None

    def _url(self) -> str:
        """Build the Deepgram streaming URL for our PCM format."""
        params = {
            "model": self._model,
            "encoding": "linear16",
            "sample_rate": str(self._sample_rate),
            "channels": "1",
            "interim_results": "true",
            "punctuate": "true",
            "smart_format": "true",
            "endpointing": "300",
            "utterance_end_ms": "1000",
            "vad_events": "true",
            "language": "en",
        }
        return f"{DEEPGRAM_WS_URL}?{urlencode(params)}"

    async def connect(self) -> None:
        """Open the WebSocket. Handles the websockets header-kwarg rename across versions."""
        url = self._url()
        headers = [("Authorization", f"Token {self._api_key}")]
        try:
            self._ws = await websockets.connect(url, additional_headers=headers, max_size=None)
        except TypeError:
            # websockets < 13 uses extra_headers
            self._ws = await websockets.connect(url, extra_headers=headers, max_size=None)
        logger.info("Deepgram stream connected (model=%s)", self._model)

    async def send_audio(self, pcm: bytes) -> None:
        """Send a chunk of raw 16-bit mono PCM to Deepgram."""
        if self._ws is not None:
            await self._ws.send(pcm)

    async def finish(self) -> None:
        """Tell Deepgram no more audio is coming so it flushes the final result."""
        if self._ws is not None:
            try:
                await self._ws.send(json.dumps({"type": "CloseStream"}))
            except Exception:
                pass

    async def close(self) -> None:
        if self._ws is not None:
            try:
                await self._ws.close()
            finally:
                self._ws = None

    async def utterances(self) -> AsyncIterator[str]:
        """Yield complete utterances as the speaker finishes each one.

        Accumulates ``is_final`` segments and emits them on ``speech_final`` or
        an ``UtteranceEnd`` event — so each yield is one complete spoken turn.
        """
        if self._ws is None:
            raise RuntimeError("Deepgram stream not connected")

        parts: list[str] = []
        async for raw in self._ws:
            try:
                msg = json.loads(raw)
            except (ValueError, TypeError):
                continue

            mtype = msg.get("type")
            if mtype == "Results":
                alternatives = msg.get("channel", {}).get("alternatives") or [{}]
                text = (alternatives[0].get("transcript") or "").strip()
                if text and msg.get("is_final"):
                    parts.append(text)
                if msg.get("speech_final") and parts:
                    yield " ".join(parts).strip()
                    parts = []
            elif mtype == "UtteranceEnd":
                if parts:
                    yield " ".join(parts).strip()
                    parts = []
