"""Per-user relay: agent audio in -> reused LiveSession -> browser SSE out.

Each logged-in user gets one ``Hub`` holding a ``BrowserPublisher`` (fan-out to
that user's browser tabs) and a ``LiveSession`` configured with the user's BYO
keys. The agent's audio WebSocket feeds the hub; the browser's SSE subscribes to it.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from src.live_session import LiveSession
from src.settings import Settings


class CloudSettings(Settings):
    """Settings backed by a single user's BYO keys — bypasses env vars / DPAPI."""

    def __init__(
        self,
        *,
        deepgram_key: str,
        anthropic_key: str,
        answer_mode: str = "GENERAL",
        persona: str = "",
        enable_web_search: bool = True,
    ) -> None:
        super().__init__()
        self._dg = deepgram_key
        self._an = anthropic_key
        self.answer_mode = answer_mode
        self.persona = persona
        self.enable_web_search = enable_web_search
        self.stt_provider = "deepgram"
        self.llm_provider = "anthropic"

    @property
    def deepgram_key(self) -> str:  # type: ignore[override]
        return self._dg

    @property
    def anthropic_key(self) -> str:  # type: ignore[override]
        return self._an

    def llm_api_key(self) -> str:
        return self._an


class BrowserPublisher:
    """Pub/sub + replayable state for one user's browser feed (mirrors src.server)."""

    def __init__(self) -> None:
        self._subs: list[asyncio.Queue[dict[str, Any]]] = []
        self.status: dict[str, Any] = {
            "recording": False, "analyzing": False, "listening": False, "call_active": False,
        }
        self.transcript: list[dict[str, Any]] = []
        self.answers: list[dict[str, Any]] = []

    # --- subscription ---
    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._subs.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        if q in self._subs:
            self._subs.remove(q)

    def _emit(self, event: dict[str, Any]) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                pass

    def snapshot(self) -> dict[str, Any]:
        return {"status": self.status, "transcript": self.transcript, "answers": self.answers}

    # --- publisher API consumed by LiveSession ---
    def update_status(self, **kwargs: Any) -> None:
        self.status.update(kwargs)
        self._emit({"type": "status", **self.status})

    def add_transcript(self, text: str, source: str = "system") -> None:
        self.transcript.append({"text": text, "source": source, "ts": time.time()})
        self._emit({"type": "transcript", "text": text, "source": source})

    def start_answer(self, answer_id: str) -> None:
        self.answers.append({"id": answer_id, "text": "", "status": "STREAMING"})
        self._emit({"type": "answer.start", "answerId": answer_id})
        self.update_status(analyzing=True)

    def stream_answer_delta(self, answer_id: str, delta: str) -> None:
        for a in self.answers:
            if a["id"] == answer_id:
                a["text"] += delta
                break
        self._emit({"type": "answer.delta", "answerId": answer_id, "text": delta})

    def finish_answer(self, answer_id: str, latency_ms: int | None = None) -> None:
        for a in self.answers:
            if a["id"] == answer_id:
                a["status"] = "DONE"
                a["latencyMs"] = latency_ms
                break
        self._emit({"type": "answer.done", "answerId": answer_id, "latencyMs": latency_ms})
        self.update_status(analyzing=False)

    def error_answer(self, answer_id: str, error: str = "") -> None:
        for a in self.answers:
            if a["id"] == answer_id:
                a["status"] = "ERROR"
                break
        self._emit({"type": "answer.error", "answerId": answer_id, "error": error})
        self.update_status(analyzing=False)


class Hub:
    """One user's live pipeline. Started when an agent connects, stopped when all leave."""

    def __init__(self, settings: CloudSettings, loop: asyncio.AbstractEventLoop) -> None:
        self.publisher = BrowserPublisher()
        self.live = LiveSession(settings, loop, publisher=self.publisher)
        self._agents = 0

    async def agent_connected(self) -> None:
        self._agents += 1
        if not self.live.is_active:
            await self.live.start()

    async def agent_disconnected(self) -> None:
        self._agents = max(0, self._agents - 1)
        if self._agents == 0 and self.live.is_active:
            await self.live.stop()

    def refresh(self, *, deepgram_key: str, anthropic_key: str,
                answer_mode: str, persona: str, enable_web_search: bool) -> None:
        """Sync the live session's settings with the user's latest DB values."""
        s = self.live._settings  # CloudSettings
        s._dg = deepgram_key  # type: ignore[attr-defined]
        s._an = anthropic_key  # type: ignore[attr-defined]
        s.answer_mode = answer_mode
        s.persona = persona
        s.enable_web_search = enable_web_search

    def feed(self, pcm: bytes) -> None:
        self.live.feed_audio(pcm)

    def force_answer(self) -> None:
        self.live.force_answer()


class HubRegistry:
    """user_id -> Hub. Hubs are created lazily on first agent connect."""

    def __init__(self) -> None:
        self._hubs: dict[int, Hub] = {}

    def get(self, user_id: int) -> Hub | None:
        return self._hubs.get(user_id)

    def get_or_create(
        self, user_id: int, settings: CloudSettings, loop: asyncio.AbstractEventLoop
    ) -> Hub:
        hub = self._hubs.get(user_id)
        if hub is None:
            hub = Hub(settings, loop)
            self._hubs[user_id] = hub
        return hub

    def drop(self, user_id: int) -> None:
        self._hubs.pop(user_id, None)
