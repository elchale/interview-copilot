"""Parallel context engine for live call mode.

Runs alongside the question gate on every finalized utterance. Instead of
answering interview questions, it gives the candidate brief situational context:
a one-line primer on a topic just mentioned, or a one-line summary after someone
finishes a long statement. It is web-search-grounded when current facts matter.

Notes are short and self-gated by the model (it emits SKIP when nothing is worth
saying), keeping the Context feed signal-dense and cheap.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import anthropic

from .prompts import build_context_system

logger = logging.getLogger(__name__)

DEFAULT_CONTEXT_MODEL = "claude-haiku-4-5"

# Basic web-search variant: the context engine runs on the cheap aux model
# (Haiku by default), which doesn't support the dynamic-filtering
# web_search_20260209 (it runs code execution under the hood — programmatic
# tool calling, unsupported on models older than Opus 4.6 / Sonnet 4.6).
WEB_SEARCH_TOOL = {"type": "web_search_20250305", "name": "web_search"}

# Kinds the engine is allowed to emit (rendered as note cards in the feed).
_NOTE_KINDS = {"summary", "fact", "topic"}


class ContextEngine:
    """Emits brief, prioritized context notes about what's being discussed."""

    def __init__(self, api_key: str, model: str | None = None, web_search: bool = True) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model or DEFAULT_CONTEXT_MODEL
        self._web_search = web_search

    async def analyze(
        self,
        context: str,
        memory: str,
        on_note: Callable[[dict[str, Any]], None],
    ) -> None:
        """Analyze the conversation and emit 0-2 short context notes.

        ``on_note`` is called with {"kind", "text", "url"} for each note and for
        each web-search query/source surfaced, so the dashboard can show both the
        commentary and what it was grounded on.
        """
        system = build_context_system(context, memory)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "max_tokens": 600,
            "system": system,
            "messages": [{"role": "user", "content": "Produce context notes for the latest exchange."}],
        }
        if self._web_search:
            kwargs["tools"] = [WEB_SEARCH_TOOL]

        try:
            # Web search runs a server-side loop that may pause; resume until done.
            text_parts: list[str] = []
            for _ in range(3):
                msg = await self._client.messages.create(**kwargs)
                for block in msg.content:
                    if getattr(block, "type", None) == "text":
                        text_parts.append(block.text)
                self._emit_sources(msg, on_note)
                if msg.stop_reason == "pause_turn":
                    kwargs["messages"] = [
                        kwargs["messages"][0],
                        {"role": "assistant", "content": msg.content},
                    ]
                    continue
                break
        except Exception as e:
            logger.warning("Context engine failed: %s", e)
            return

        for note in self._parse_notes("".join(text_parts)):
            on_note(note)

    @staticmethod
    def _parse_notes(text: str) -> list[dict[str, str]]:
        """Parse 'NOTE|<kind>|<text>' lines into note dicts (ignores SKIP/noise)."""
        notes: list[dict[str, str]] = []
        for raw in text.splitlines():
            line = raw.strip()
            if not line.startswith("NOTE|"):
                continue
            parts = line.split("|", 2)
            if len(parts) != 3:
                continue
            kind = parts[1].strip().lower()
            body = parts[2].strip()
            if not body:
                continue
            if kind not in _NOTE_KINDS:
                kind = "topic"
            notes.append({"kind": kind, "text": body, "url": ""})
        return notes[:2]

    @staticmethod
    def _emit_sources(msg: Any, on_note: Callable[[dict[str, Any]], None]) -> None:
        """Surface the web-search queries/sources the engine used, for transparency."""
        for block in getattr(msg, "content", []) or []:
            btype = getattr(block, "type", None)
            if btype == "server_tool_use" and getattr(block, "name", None) == "web_search":
                inp = getattr(block, "input", None)
                query = str(inp.get("query")) if isinstance(inp, dict) and inp.get("query") else ""
                if query:
                    on_note({"kind": "query", "text": query, "url": ""})
            elif btype == "web_search_tool_result":
                for r in getattr(block, "content", None) or []:
                    if getattr(r, "type", None) == "web_search_result":
                        on_note({
                            "kind": "source",
                            "text": getattr(r, "title", "") or getattr(r, "url", ""),
                            "url": getattr(r, "url", "") or "",
                        })
