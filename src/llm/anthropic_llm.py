"""Anthropic Claude LLM provider."""

from __future__ import annotations

import logging
from typing import AsyncIterator

import anthropic

from .prompts import build_user_message

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"


class AnthropicProvider:
    """Stream answers using Anthropic's Claude API with prompt caching."""

    def __init__(self, api_key: str, model: str | None = None) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model or DEFAULT_MODEL

    @property
    def name(self) -> str:
        return "anthropic"

    async def stream_answer(
        self,
        transcript: str,
        mode: str = "GENERAL",
        persona: str = "",
    ) -> AsyncIterator[str]:
        system_prompt, user_msg = build_user_message(transcript, mode, persona)

        async with self._client.messages.stream(
            model=self._model,
            max_tokens=1536,
            system=[
                {
                    "type": "text",
                    "text": system_prompt,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_msg}],
        ) as stream:
            async for event in stream:
                if event.type == "content_block_delta" and hasattr(event.delta, "text"):
                    yield event.delta.text
