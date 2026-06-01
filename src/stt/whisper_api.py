"""OpenAI Whisper API STT provider."""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

WHISPER_URL = "https://api.openai.com/v1/audio/transcriptions"


class WhisperAPIProvider:
    """Transcribe audio using OpenAI's Whisper API."""

    def __init__(self, api_key: str, model: str = "whisper-1") -> None:
        self._api_key = api_key
        self._model = model

    @property
    def name(self) -> str:
        return "whisper_api"

    async def transcribe(self, audio_path: str) -> str:
        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        async with httpx.AsyncClient(timeout=120.0) as client:
            with open(path, "rb") as f:
                resp = await client.post(
                    WHISPER_URL,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    files={"file": (path.name, f, "audio/ogg")},
                    data={
                        "model": self._model,
                        "response_format": "text",
                        "language": "en",
                    },
                )
            resp.raise_for_status()
            text = resp.text.strip()
            logger.info("Whisper transcribed %d chars from %s", len(text), path.name)
            return text
