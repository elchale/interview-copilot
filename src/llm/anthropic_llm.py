"""Anthropic Claude LLM provider."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Callable

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
        on_context: Callable[[dict[str, Any]], None] | None = None,
    ) -> AsyncIterator[str]:
        """Stream a live-mode answer, optionally grounded with server-side web search.

        ``on_context`` (if given) is called for each web-search query Claude issues and
        each source it pulls back, so the dashboard can show what's being researched.
        """
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

            if on_context is not None:
                self._emit_context(final, on_context)

            if final.stop_reason == "pause_turn":
                kwargs["messages"] = [
                    {"role": "user", "content": question},
                    {"role": "assistant", "content": final.content},
                ]
                continue
            break

    @staticmethod
    def _emit_context(final: Any, on_context: Callable[[dict[str, Any]], None]) -> None:
        """Pull web-search queries and result sources out of a finished message."""
        for block in getattr(final, "content", []) or []:
            btype = getattr(block, "type", None)
            if btype == "server_tool_use" and getattr(block, "name", None) == "web_search":
                query = ""
                inp = getattr(block, "input", None)
                if isinstance(inp, dict):
                    query = str(inp.get("query") or "")
                if query:
                    on_context({"kind": "query", "text": query, "url": ""})
            elif btype == "web_search_tool_result":
                for r in getattr(block, "content", None) or []:
                    if getattr(r, "type", None) == "web_search_result":
                        on_context({
                            "kind": "source",
                            "text": getattr(r, "title", "") or getattr(r, "url", ""),
                            "url": getattr(r, "url", "") or "",
                        })
