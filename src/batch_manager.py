"""Batch manager: encodes PCM audio to Opus segments, manages storage and cleanup."""

from __future__ import annotations

import asyncio
import logging
import shutil
import struct
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from queue import Queue, Empty

from .settings import BATCHES_DIR

logger = logging.getLogger(__name__)

SAMPLE_RATE = 16000


class BatchManager:
    """Collects PCM frames from queues and writes Opus-encoded batch files."""

    def __init__(
        self,
        batch_duration: int = 60,
        retention_hours: int = 48,
    ) -> None:
        self._batch_duration = batch_duration
        self._retention_hours = retention_hours
        self._running = False
        self._threads: list[threading.Thread] = []
        self._ffmpeg = shutil.which("ffmpeg")
        BATCHES_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def is_running(self) -> bool:
        return self._running

    def start(
        self,
        system_queue: Queue[bytes],
        mic_queue: Queue[bytes],
    ) -> None:
        if self._running:
            return
        self._running = True
        self._threads = [
            threading.Thread(
                target=self._encode_loop,
                args=(system_queue, "sys"),
                daemon=True,
                name="batch-sys",
            ),
            threading.Thread(
                target=self._encode_loop,
                args=(mic_queue, "mic"),
                daemon=True,
                name="batch-mic",
            ),
            threading.Thread(
                target=self._cleanup_loop,
                daemon=True,
                name="batch-cleanup",
            ),
        ]
        for t in self._threads:
            t.start()
        logger.info("BatchManager started (dur=%ds, retention=%dh)", self._batch_duration, self._retention_hours)

    def stop(self) -> None:
        self._running = False
        for t in self._threads:
            t.join(timeout=5)
        self._threads.clear()

    def get_recent_batches(
        self,
        source: str = "sys",
        seconds: int = 180,
    ) -> list[Path]:
        """Return batch files from the last N seconds, newest last."""
        cutoff = datetime.now() - timedelta(seconds=seconds)
        pattern = f"{source}_*.opus"
        batches: list[tuple[datetime, Path]] = []

        for p in BATCHES_DIR.glob(pattern):
            try:
                ts_str = p.stem.split("_", 1)[1]
                ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
                if ts >= cutoff:
                    batches.append((ts, p))
            except (ValueError, IndexError):
                continue

        batches.sort(key=lambda x: x[0])
        return [p for _, p in batches]

    def merge_batches(self, batch_paths: list[Path], output_path: Path) -> bool:
        """Concatenate multiple Opus batches into a single file using ffmpeg."""
        if not batch_paths:
            return False
        if not self._ffmpeg:
            if len(batch_paths) == 1:
                shutil.copy2(batch_paths[0], output_path)
                return True
            logger.error("ffmpeg not found — cannot merge batches")
            return False

        list_file = output_path.with_suffix(".txt")
        try:
            list_file.write_text(
                "\n".join(f"file '{p.resolve()}'" for p in batch_paths),
                encoding="utf-8",
            )
            import subprocess
            result = subprocess.run(
                [
                    self._ffmpeg, "-y", "-f", "concat", "-safe", "0",
                    "-i", str(list_file), "-c", "copy", str(output_path),
                ],
                capture_output=True,
                timeout=30,
            )
            return result.returncode == 0
        except Exception as e:
            logger.error("Batch merge failed: %s", e)
            return False
        finally:
            list_file.unlink(missing_ok=True)

    def disk_usage_mb(self) -> float:
        total = sum(f.stat().st_size for f in BATCHES_DIR.rglob("*") if f.is_file())
        return total / (1024 * 1024)

    def _encode_loop(self, audio_queue: Queue[bytes], prefix: str) -> None:
        """Collect PCM frames from the queue and write Opus batch files."""
        buffer = bytearray()
        batch_bytes = SAMPLE_RATE * 2 * self._batch_duration  # 16-bit mono

        while self._running:
            try:
                chunk = audio_queue.get(timeout=0.5)
                buffer.extend(chunk)
            except Empty:
                continue

            if len(buffer) >= batch_bytes:
                self._write_batch(bytes(buffer[:batch_bytes]), prefix)
                buffer = buffer[batch_bytes:]

        # Flush remaining
        if buffer:
            self._write_batch(bytes(buffer), prefix)

    def _write_batch(self, pcm_data: bytes, prefix: str) -> None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = BATCHES_DIR / f"{prefix}_{ts}.opus"

        if self._ffmpeg:
            self._encode_opus(pcm_data, output)
        else:
            # Fallback: save raw PCM (much larger, but works without ffmpeg)
            raw_path = output.with_suffix(".raw")
            raw_path.write_bytes(pcm_data)
            logger.warning("ffmpeg not found — saved raw PCM: %s", raw_path.name)

    def _encode_opus(self, pcm_data: bytes, output: Path) -> None:
        """Encode raw PCM to Opus via ffmpeg subprocess."""
        import subprocess

        try:
            result = subprocess.run(
                [
                    self._ffmpeg, "-y",
                    "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1",
                    "-i", "pipe:0",
                    "-c:a", "libopus", "-b:a", "16k",
                    "-application", "voip",
                    str(output),
                ],
                input=pcm_data,
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0:
                size_kb = output.stat().st_size / 1024
                logger.debug("Wrote batch %s (%.1f KB)", output.name, size_kb)
            else:
                logger.error("ffmpeg encode failed: %s", result.stderr.decode()[:200])
        except Exception as e:
            logger.error("Opus encoding error: %s", e)

    def _cleanup_loop(self) -> None:
        """Delete batches older than retention period."""
        while self._running:
            cutoff = datetime.now() - timedelta(hours=self._retention_hours)
            deleted = 0
            for p in BATCHES_DIR.iterdir():
                if not p.is_file():
                    continue
                try:
                    ts_str = p.stem.split("_", 1)[1]
                    ts = datetime.strptime(ts_str, "%Y%m%d_%H%M%S")
                    if ts < cutoff:
                        p.unlink()
                        deleted += 1
                except (ValueError, IndexError):
                    continue

            if deleted:
                logger.info("Cleaned up %d old batch files", deleted)

            # Run cleanup every 10 minutes
            for _ in range(600):
                if not self._running:
                    return
                time.sleep(1)
