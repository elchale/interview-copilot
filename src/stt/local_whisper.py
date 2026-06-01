"""Local Whisper (whisper.cpp) STT provider — no API key needed."""

from __future__ import annotations

import asyncio
import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)


class LocalWhisperProvider:
    """Transcribe audio using a local whisper.cpp binary."""

    def __init__(self, binary: str | None = None, model_path: str | None = None) -> None:
        self._binary = binary or shutil.which("whisper-cpp") or shutil.which("main")
        self._model = model_path or ""

    @property
    def name(self) -> str:
        return "local"

    async def transcribe(self, audio_path: str) -> str:
        if not self._binary:
            raise RuntimeError(
                "whisper.cpp binary not found. Install it or set the path in settings."
            )

        path = Path(audio_path)
        if not path.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        wav_path = path.with_suffix(".wav")
        ffmpeg = shutil.which("ffmpeg")
        if not ffmpeg:
            raise RuntimeError("ffmpeg not found — required to decode audio for local whisper")

        # Decode to 16kHz mono WAV (whisper.cpp requirement)
        decode = await asyncio.create_subprocess_exec(
            ffmpeg, "-y", "-i", str(path),
            "-ar", "16000", "-ac", "1", "-f", "wav", str(wav_path),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await decode.wait()

        cmd = [self._binary, "-f", str(wav_path), "--no-timestamps", "-nt"]
        if self._model:
            cmd.extend(["-m", self._model])

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        stdout, _ = await proc.communicate()
        text = stdout.decode("utf-8", errors="replace").strip()

        wav_path.unlink(missing_ok=True)

        logger.info("Local whisper transcribed %d chars from %s", len(text), path.name)
        return text
