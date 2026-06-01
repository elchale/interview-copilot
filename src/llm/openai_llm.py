"""OpenAI GPT LLM provider."""

from __future__ import annotations

import logging
from typing import AsyncIterator

from openai import AsyncOpenAI

from .prompts import build_user_message

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o"


class OpenAIProvider:
    """Stream answers using OpenAI's Chat Completions API."""

    def __init__(self, api_key: str, model: str | None = None) -> None:
        self._client = AsyncOpenAI(api_key=api_key)
        self._model = model or DEFAULT_MODEL

    @property
    def name(self) -> str:
        return "openai"

    async def stream_answer(
        self,
        transcript: str,
        mode: str = "GENERAL",
        persona: str = "",
    ) -> AsyncIterator[str]:
        system_prompt, user_msg = build_user_message(transcript, mode, persona)

        stream = await self._client.chat.completions.create(
            model=self._model,
            max_tokens=1536,
            stream=True,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_msg},
            ],
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content
