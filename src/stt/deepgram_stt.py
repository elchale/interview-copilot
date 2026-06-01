"""Deepgram Nova-3 STT provider."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"


class DeepgramProvider:
    """Transcribe audio using Deepgram's Nova-3 model."""

    def __init__(self, api_key: str, model: str = "nova-3") -> None:
        self._api_key = api_key
        self._model = model

    @property
    def name(self) -> str:
        return "deepgram"

    async def transcribe(self, audio_path: str) -> str:
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        params = {
            "model": self._model,
            "smart_format": "true",
            "punctuate": "true",
            "language": "en",
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            with open(path, "rb") as f:
                resp = await client.post(
                    DEEPGRAM_URL,
                    params=params,
                    headers={
                        "Authorization": f"Token {self._api_key}",
                        "Content-Type": "audio/ogg",
                    },
                    content=f.read(),
                )
            resp.raise_for_status()
            data = resp.json()

        transcript_parts: list[str] = []
        for channel in data.get("results", {}).get("channels", []):
            for alt in channel.get("alternatives", []):
                if alt.get("transcript"):
                    transcript_parts.append(alt["transcript"])

        text = " ".join(transcript_parts).strip()
        logger.info("Deepgram transcribed %d chars from %s", len(text), path.name)
        return text
