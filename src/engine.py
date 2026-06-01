"""Core engine: orchestrates recording → batch storage → STT → LLM on trigger."""

from __future__ import annotations

import asyncio
import logging
import tempfile
import time
import uuid
from pathlib import Path

from .batch_manager import BatchManager
from .recorder import Recorder
from .settings import Settings
from . import server
from .stt import get_provider as get_stt
from .llm import get_provider as get_llm

logger = logging.getLogger(__name__)


class Engine:
    """Central engine that ties recorder, batch manager, and AI providers together."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._recorder = Recorder(loopback_device_index=settings.loopback_device_index)
        self._batch_mgr = BatchManager(
            batch_duration=settings.batch_duration_seconds,
            retention_hours=settings.retention_hours,
        )
        self._loop: asyncio.AbstractEventLoop | None = None
        self._listening = False
        self._analyzing = False

    @property
    def is_listening(self) -> bool:
        return self._listening

    @property
    def is_analyzing(self) -> bool:
        return self._analyzing

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def start_listening(self) -> None:
        if self._listening:
            return
        self._recorder.start()
        self._batch_mgr.start(self._recorder.system_queue, self._recorder.mic_queue)
        self._listening = True
        server.update_status(listening=True, recording=True)
        logger.info("Listening started")

    def stop_listening(self) -> None:
        if not self._listening:
            return
        self._recorder.stop()
        self._batch_mgr.stop()
        self._listening = False
        server.update_status(listening=False, recording=False)
        logger.info("Listening stopped")

    def toggle_listening(self) -> None:
        if self._listening:
            self.stop_listening()
        else:
            self.start_listening()

    def answer_latest(self) -> None:
        """Trigger AI analysis of recent audio. Thread-safe — can be called from hotkey."""
        if self._analyzing:
            logger.warning("Already analyzing — ignoring trigger")
            return
        if self._loop:
            asyncio.run_coroutine_threadsafe(self._do_answer(), self._loop)
        else:
            logger.error("No event loop set — cannot run answer")

    async def _do_answer(self) -> None:
        self._analyzing = True
        answer_id = str(uuid.uuid4())[:8]
        t0 = time.monotonic()

        try:
            # Gather recent batches
            batches = self._batch_mgr.get_recent_batches(
                source="sys",
                seconds=self.settings.answer_window_seconds,
            )
            if not batches:
                logger.warning("No recent audio batches to analyze")
                server.start_answer(answer_id)
                server.error_answer(answer_id, "No recent audio recorded")
                return

            # Merge batches into a single file
            merged = Path(tempfile.mktemp(suffix=".opus"))
            if not self._batch_mgr.merge_batches(batches, merged):
                server.start_answer(answer_id)
                server.error_answer(answer_id, "Failed to merge audio batches")
                return

            # Transcribe
            stt_key = self.settings.stt_api_key()
            stt = get_stt(self.settings.stt_provider, stt_key)
            logger.info("Transcribing %d batches via %s...", len(batches), stt.name)
            transcript = await stt.transcribe(str(merged))
            merged.unlink(missing_ok=True)

            if not transcript.strip():
                server.start_answer(answer_id)
                server.error_answer(answer_id, "No speech detected in audio")
                return

            # Publish transcript
            server.add_transcript(transcript, source="system")

            # Stream LLM answer
            llm_key = self.settings.llm_api_key()
            llm_model = self.settings.llm_model or None
            llm = get_llm(self.settings.llm_provider, llm_key, llm_model)

            server.start_answer(answer_id)
            first_token = True
            latency_ms: int | None = None

            async for token in llm.stream_answer(
                transcript=transcript,
                mode=self.settings.answer_mode,
                persona=self.settings.persona,
            ):
                if first_token:
                    latency_ms = int((time.monotonic() - t0) * 1000)
                    first_token = False
                server.stream_answer_delta(answer_id, token)

            server.finish_answer(answer_id, latency_ms=latency_ms)
            logger.info(
                "Answer %s complete (first token: %s ms, provider: %s)",
                answer_id, latency_ms, llm.name,
            )

        except Exception as e:
            logger.exception("Answer generation failed")
            server.start_answer(answer_id)
            server.error_answer(answer_id, str(e))
        finally:
            self._analyzing = False

    def disk_usage_mb(self) -> float:
        return self._batch_mgr.disk_usage_mb()
