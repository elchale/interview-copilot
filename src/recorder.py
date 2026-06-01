"""Audio capture: WASAPI loopback (system audio) + microphone."""

from __future__ import annotations

import logging
import queue
import struct
import threading
import time
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)

SAMPLE_RATE = 48000
CHANNELS_MONO = 1
FRAME_DURATION_MS = 30
FRAMES_PER_BUFFER = int(SAMPLE_RATE * FRAME_DURATION_MS / 1000)


def loopback_devices() -> list[tuple[int, str]]:
    """List available WASAPI loopback devices."""
    try:
        import pyaudiowpatch as pyaudio
    except ImportError:
        return []

    pa = pyaudio.PyAudio()
    devices: list[tuple[int, str]] = []
    try:
        wasapi_info = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
        for i in range(pa.get_device_count()):
            dev = pa.get_device_info_by_index(i)
            if dev["hostApi"] == wasapi_info["index"] and dev.get("isLoopbackDevice", False):
                devices.append((i, dev["name"]))
    except Exception as e:
        logger.warning("Failed to enumerate loopback devices: %s", e)
    finally:
        pa.terminate()
    return devices


class Recorder:
    """Dual-stream audio recorder: system loopback + microphone."""

    def __init__(
        self,
        loopback_device_index: int | None = None,
        on_system_audio: Callable[[bytes], None] | None = None,
        on_mic_audio: Callable[[bytes], None] | None = None,
    ) -> None:
        self._loopback_idx = loopback_device_index
        self._on_system = on_system_audio
        self._on_mic = on_mic_audio
        self._running = False
        self._threads: list[threading.Thread] = []
        self.system_queue: queue.Queue[bytes] = queue.Queue(maxsize=500)
        self.mic_queue: queue.Queue[bytes] = queue.Queue(maxsize=500)

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._threads = [
            threading.Thread(target=self._capture_loopback, daemon=True, name="loopback"),
            threading.Thread(target=self._capture_mic, daemon=True, name="mic"),
        ]
        for t in self._threads:
            t.start()
        logger.info("Recorder started (loopback_idx=%s)", self._loopback_idx)

    def stop(self) -> None:
        self._running = False
        for t in self._threads:
            t.join(timeout=3)
        self._threads.clear()
        logger.info("Recorder stopped")

    def _capture_loopback(self) -> None:
        try:
            import pyaudiowpatch as pyaudio
        except ImportError:
            logger.error("PyAudioWPatch not installed — cannot capture system audio")
            return

        pa = pyaudio.PyAudio()
        try:
            if self._loopback_idx is not None:
                dev = pa.get_device_info_by_index(self._loopback_idx)
            else:
                wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
                dev = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
                for i in range(pa.get_device_count()):
                    d = pa.get_device_info_by_index(i)
                    if d.get("isLoopbackDevice") and d["hostApi"] == wasapi["index"]:
                        dev = d
                        break

            native_rate = int(dev["defaultSampleRate"])
            native_channels = max(dev["maxInputChannels"], 1)

            stream = pa.open(
                format=pyaudio.paInt16,
                channels=native_channels,
                rate=native_rate,
                input=True,
                input_device_index=dev["index"],
                frames_per_buffer=int(native_rate * FRAME_DURATION_MS / 1000),
            )

            logger.info(
                "Loopback: %s @ %dHz, %d ch",
                dev["name"], native_rate, native_channels,
            )

            while self._running:
                try:
                    data = stream.read(
                        int(native_rate * FRAME_DURATION_MS / 1000),
                        exception_on_overflow=False,
                    )
                except OSError:
                    time.sleep(0.1)
                    continue

                mono = self._to_mono_16k(data, native_rate, native_channels)
                try:
                    self.system_queue.put_nowait(mono)
                except queue.Full:
                    self.system_queue.get_nowait()
                    self.system_queue.put_nowait(mono)

                if self._on_system:
                    self._on_system(mono)

            stream.stop_stream()
            stream.close()
        except Exception as e:
            logger.error("Loopback capture error: %s", e)
        finally:
            pa.terminate()

    def _capture_mic(self) -> None:
        try:
            import pyaudiowpatch as pyaudio
        except ImportError:
            logger.error("PyAudioWPatch not installed — cannot capture mic")
            return

        pa = pyaudio.PyAudio()
        try:
            dev = pa.get_default_input_device_info()
            native_rate = int(dev["defaultSampleRate"])
            native_channels = max(dev["maxInputChannels"], 1)

            stream = pa.open(
                format=pyaudio.paInt16,
                channels=native_channels,
                rate=native_rate,
                input=True,
                frames_per_buffer=int(native_rate * FRAME_DURATION_MS / 1000),
            )

            logger.info("Mic: %s @ %dHz", dev["name"], native_rate)

            while self._running:
                try:
                    data = stream.read(
                        int(native_rate * FRAME_DURATION_MS / 1000),
                        exception_on_overflow=False,
                    )
                except OSError:
                    time.sleep(0.1)
                    continue

                mono = self._to_mono_16k(data, native_rate, native_channels)
                try:
                    self.mic_queue.put_nowait(mono)
                except queue.Full:
                    self.mic_queue.get_nowait()
                    self.mic_queue.put_nowait(mono)

                if self._on_mic:
                    self._on_mic(mono)

            stream.stop_stream()
            stream.close()
        except Exception as e:
            logger.error("Mic capture error: %s", e)
        finally:
            pa.terminate()

    @staticmethod
    def _to_mono_16k(data: bytes, source_rate: int, channels: int) -> bytes:
        """Downmix to mono and resample to 16kHz for storage efficiency."""
        samples = np.frombuffer(data, dtype=np.int16)

        if channels > 1:
            samples = samples.reshape(-1, channels).mean(axis=1).astype(np.int16)

        if source_rate != 16000:
            target_len = int(len(samples) * 16000 / source_rate)
            indices = np.linspace(0, len(samples) - 1, target_len).astype(int)
            samples = samples[indices]

        return samples.tobytes()
