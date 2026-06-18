"""Live call mode: continuous streaming STT, auto question detection, instant answers.

On "start call", system audio (the interviewer) streams continuously to Deepgram.
Each finalized utterance is appended to a rolling context buffer and passed through
the question gate; anything that needs an answer is sent to the LLM (with web search)
and streamed to the dashboard immediately — no keypress, minimal latency.
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections import deque

from . import server
from .llm import get_provider as get_llm
from .llm.gate import QuestionGate
from .settings import Settings
from .stt.deepgram_stream import DeepgramStream

logger = logging.getLogger(__name__)


class LiveSession:
    """Drives a live interview call: audio → transcript → gate → streamed answer."""

    def __init__(
        self,
        settings: Settings,
        loop: asyncio.AbstractEventLoop,
        publisher=server,
    ) -> None:
        self._settings = settings
        self._loop = loop
        # `publisher` is any object exposing add_transcript/start_answer/
        # stream_answer_delta/finish_answer/error_answer/update_status. Defaults
        # to the local server module; the cloud backend injects a per-user one.
        self._pub = publisher
        self._active = False
        self._audio_q: asyncio.Queue[bytes] = asyncio.Queue(maxsize=2000)
        self._stream: DeepgramStream | None = None
        self._gate: QuestionGate | None = None
        self._tasks: list[asyncio.Task] = []
        self._context: deque[str] = deque(maxlen=max(4, settings.live_context_utterances))
        self._answer_lock = asyncio.Lock()

    @property
    def is_active(self) -> bool:
        return self._active

    def feed_audio(self, pcm: bytes) -> None:
        """Thread-safe hand-off of PCM frames from the recorder capture thread."""
        if not self._active:
            return
        try:
            self._loop.call_soon_threadsafe(self._enqueue, pcm)
        except RuntimeError:
            pass

    def _enqueue(self, pcm: bytes) -> None:
        try:
            self._audio_q.put_nowait(pcm)
        except asyncio.QueueFull:
            # Drop oldest to stay near real time
            try:
                self._audio_q.get_nowait()
                self._audio_q.put_nowait(pcm)
            except asyncio.QueueEmpty:
                pass

    async def start(self) -> None:
        if self._active:
            return

        dg_key = self._settings.deepgram_key
        if not dg_key:
            self._report_error("Live mode needs a Deepgram API key — set it in the control menu.")
            logger.error("Live mode: no Deepgram key configured")
            return

        if not self._settings.llm_api_key():
            self._report_error("Live mode needs an LLM API key.")
            logger.error("Live mode: no LLM key configured")
            return

        gate_key = self._settings.anthropic_key or self._settings.llm_api_key()
        self._gate = QuestionGate(gate_key, self._settings.live_gate_model)
        self._stream = DeepgramStream(dg_key)
        try:
            await self._stream.connect()
        except Exception as e:
            logger.exception("Deepgram connect failed")
            self._report_error(f"Could not start live transcription: {e}")
            self._stream = None
            return

        self._active = True
        self._pub.update_status(call_active=True, listening=True, recording=True)
        self._tasks = [
            asyncio.create_task(self._sender(), name="live-sender"),
            asyncio.create_task(self._receiver(), name="live-receiver"),
        ]
        logger.info("Live call started")

    async def stop(self) -> None:
        if not self._active:
            return
        self._active = False
        if self._stream is not None:
            await self._stream.finish()
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()
        if self._stream is not None:
            await self._stream.close()
            self._stream = None
        self._pub.update_status(call_active=False)
        logger.info("Live call stopped")

    async def _sender(self) -> None:
        try:
            while self._active:
                pcm = await self._audio_q.get()
                if self._stream is not None:
                    await self._stream.send_audio(pcm)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Live audio sender stopped unexpectedly")

    async def _receiver(self) -> None:
        try:
            assert self._stream is not None
            async for utterance in self._stream.utterances():
                if not utterance:
                    continue
                self._context.append(f"Interviewer: {utterance}")
                self._pub.add_transcript(utterance, source="system")
                asyncio.create_task(self._maybe_answer(utterance))
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Live transcript receiver stopped unexpectedly")

    async def _maybe_answer(self, utterance: str) -> None:
        if self._gate is None:
            return
        try:
            needs, question = await self._gate.classify("\n".join(self._context), utterance)
        except Exception:
            logger.exception("Question gate failed")
            return
        if not needs:
            return
        async with self._answer_lock:
            await self._answer(question)

    def force_answer(self) -> None:
        """Force an answer on the latest context — the panic / manual hotkey."""
        if not self._active:
            return
        ctx = list(self._context)
        question = ctx[-1].split("Interviewer: ", 1)[-1] if ctx else "Help me respond right now."
        asyncio.run_coroutine_threadsafe(self._forced(question), self._loop)

    async def _forced(self, question: str) -> None:
        async with self._answer_lock:
            await self._answer(question)

    async def _answer(self, question: str) -> None:
        answer_id = str(uuid.uuid4())[:8]
        t0 = time.monotonic()
        try:
            llm = get_llm(
                self._settings.llm_provider,
                self._settings.llm_api_key(),
                self._settings.llm_model or None,
            )
            context = "\n".join(self._context)
            self._pub.start_answer(answer_id)

            stream_live = getattr(llm, "stream_live_answer", None)
            if stream_live is not None:
                agen = stream_live(
                    question=question,
                    context=context,
                    mode=self._settings.answer_mode,
                    persona=self._settings.persona,
                    web_search=self._settings.enable_web_search,
                )
            else:
                # Provider without a live method — fall back to the batch answer path.
                transcript = f"{context}\n\nQUESTION: {question}"
                agen = llm.stream_answer(
                    transcript=transcript,
                    mode=self._settings.answer_mode,
                    persona=self._settings.persona,
                )

            first = True
            latency_ms: int | None = None
            async for token in agen:
                if first:
                    latency_ms = int((time.monotonic() - t0) * 1000)
                    first = False
                self._pub.stream_answer_delta(answer_id, token)
            self._pub.finish_answer(answer_id, latency_ms=latency_ms)
            logger.info("Live answer %s complete (first token: %s ms)", answer_id, latency_ms)
        except Exception as e:
            logger.exception("Live answer generation failed")
            self._pub.error_answer(answer_id, str(e))

    @staticmethod
    def _report_error(message: str) -> None:
        answer_id = str(uuid.uuid4())[:8]
        self._pub.start_answer(answer_id)
        server.error_answer(answer_id, message)
