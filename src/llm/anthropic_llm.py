"""Anthropic Claude LLM provider."""

from __future__ import annotations

import logging
from typing import AsyncIterator

import anthropic

from .prompts import build_live_system, build_user_message

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "claude-sonnet-4-6"

# Server-side web search tool (dynamic filtering on Sonnet 4.6 / Opus 4.x).
WEB_SEARCH_TOOL = {"type": "web_search_20260209", "name": "web_search"}


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

    async def stream_live_answer(
        self,
        question: str,
        context: str,
        mode: str = "GENERAL",
        persona: str = "",
        web_search: bool = True,
    ) -> AsyncIterator[str]:
        """Stream a live-mode answer, optionally grounded with server-side web search."""
        system = build_live_system(mode, persona, context)

        kwargs: dict = {
            "model": self._model,
            "max_tokens": 1024,
            "system": system,
            "messages": [{"role": "user", "content": question}],
        }
        if web_search:
            kwargs["tools"] = [WEB_SEARCH_TOOL]

        # Web search runs a server-side loop that may pause; resume until done.
        for _ in range(4):
            async with self._client.messages.stream(**kwargs) as stream:
                async for event in stream:
                    if event.type == "content_block_delta" and getattr(event.delta, "type", None) == "text_delta":
                        yield event.delta.text
                final = await stream.get_final_message()

            if final.stop_reason == "pause_turn":
                kwargs["messages"] = [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": final.content},
                ]
                continue
            break
