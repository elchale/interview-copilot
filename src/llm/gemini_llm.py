"""Google Gemini LLM provider."""

from __future__ import annotations

import logging
from typing import AsyncIterator

from google import genai
from google.genai import types

from .prompts import build_user_message

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-2.5-pro"


class GeminiProvider:
    """Stream answers using Google's Gemini API."""

    def __init__(self, api_key: str, model: str | None = None) -> None:
        self._client = genai.Client(api_key=api_key)
        self._model = model or DEFAULT_MODEL

    @property
    def name(self) -> str:
        return "gemini"

    async def stream_answer(
        self,
        transcript: str,
        mode: str = "GENERAL",
        persona: str = "",
    ) -> AsyncIterator[str]:
        system_prompt, user_msg = build_user_message(transcript, mode, persona)

        response = self._client.models.generate_content_stream(
            model=self._model,
            contents=user_msg,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                max_output_tokens=1536,
            ),
        )

        for chunk in response:
            if chunk.text:
                yield chunk.text
