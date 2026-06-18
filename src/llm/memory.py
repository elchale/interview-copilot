"""Rolling session memory for live call mode.

A cheap, fast model (Haiku by default) keeps a terse running memory of the
people, facts, and topics established during the call. It is injected into the
answer and context prompts so the copilot stays consistent and "remembers"
names and claims without re-reading the whole transcript every time.

Updates run in the background, debounced, so they never block answers.
"""

from __future__ import annotations

import asyncio
import logging

import anthropic

from .prompts import MEMORY_SYSTEM_PROMPT, build_memory_user

logger = logging.getLogger(__name__)

DEFAULT_MEMORY_MODEL = "claude-haiku-4-5"


class SessionMemory:
    """Maintains a concise, evolving memory of the current call."""

    def __init__(self, api_key: str, model: str | None = None) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key)
        self._model = model or DEFAULT_MEMORY_MODEL
        self._summary: str = ""
        self._lock = asyncio.Lock()

    def render(self) -> str:
        """Current memory text, safe to embed in a prompt."""
        return self._summary

    async def update(self, new_lines: list[str]) -> None:
        """Merge new transcript lines into the running memory (best-effort)."""
        lines = "\n".join(line for line in new_lines if line.strip())
        if not lines:
            return
        async with self._lock:
            try:
                resp = await self._client.messages.create(
                    model=self._model,
                    max_tokens=400,
                    system=MEMORY_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": build_memory_user(self._summary, lines)}],
                )
                text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
                if text.strip():
                    self._summary = text.strip()
            except Exception as e:
                logger.warning("Session memory update failed: %s", e)
