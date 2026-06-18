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

# PortAudio's global init/terminate is not thread-safe; serialize PyAudio()
# construction across the loopback and mic threads to avoid native crashes.
_PA_LOCK = threading.Lock()


class _NoMic(Exception):
    """No default input device available right now."""

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
        capture_mic: bool = True,
    ) -> None:
        self._loopback_idx = loopback_device_index
        self._on_system = on_system_audio
        self._on_mic = on_mic_audio
        self._mic_enabled = capture_mic
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
        ]
        if self._mic_enabled:
            self._threads.append(
                threading.Thread(target=self._capture_mic, daemon=True, name="mic")
            )
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

        with _PA_LOCK:
            pa = pyaudio.PyAudio()
        try:
            if self._loopback_idx is not None:
                dev = pa.get_device_info_by_index(self._loopback_idx)
            else:
                wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
                default_out = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
                dev = None
                # Prefer the loopback that matches the current default output device
                # (so we capture whatever the user is actually listening through).
                for i in range(pa.get_device_count()):
                    d = pa.get_device_info_by_index(i)
                    if d.get("isLoopbackDevice") and default_out["name"] in d["name"]:
                        dev = d
                        break
                if dev is None:  # fall back to the first available loopback
                    for i in range(pa.get_device_count()):
                        d = pa.get_device_info_by_index(i)
                        if d.get("isLoopbackDevice"):
                            dev = d
                            break
                if dev is None:
                    dev = default_out

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
        """Capture the default mic, re-detecting the device on a short interval so
        a mic connected mid-session starts working and a disconnected one doesn't
        crash the recorder."""
        try:
            import pyaudiowpatch as pyaudio
        except ImportError:
            logger.error("PyAudioWPatch not installed — cannot capture mic")
            return

        current_name: str | None = None
        while self._running:
            pa = None
            stream = None
            try:
                with _PA_LOCK:
                    pa = pyaudio.PyAudio()
                try:
                    dev = pa.get_default_input_device_info()
                except Exception:
                    if current_name is not None:
                        logger.info("Mic disconnected — waiting for a device")
                        current_name = None
                    raise _NoMic()

                native_rate = int(dev["defaultSampleRate"])
                native_channels = max(dev["maxInputChannels"], 1)
                frames = int(native_rate * FRAME_DURATION_MS / 1000)
                stream = pa.open(
                    format=pyaudio.paInt16,
                    channels=native_channels,
                    rate=native_rate,
                    input=True,
                    input_device_index=dev["index"],
                    frames_per_buffer=frames,
                )
                if dev["name"] != current_name:
                    current_name = dev["name"]
                    logger.info("Mic: %s @ %dHz", current_name, native_rate)

                while self._running:
                    try:
                        data = stream.read(frames, exception_on_overflow=False)
                    except OSError:
                        break  # device changed/unplugged — drop out and re-detect
                    mono = self._to_mono_16k(data, native_rate, native_channels)
                    try:
                        self.mic_queue.put_nowait(mono)
                    except queue.Full:
                        self.mic_queue.get_nowait()
                        self.mic_queue.put_nowait(mono)
                    if self._on_mic:
                        self._on_mic(mono)
            except _NoMic:
                pass
            except Exception as e:
                logger.error("Mic capture error: %s", e)
            finally:
                if stream is not None:
                    try:
                        stream.stop_stream()
                        stream.close()
                    except Exception:
                        pass
                if pa is not None:
                    with _PA_LOCK:
                        pa.terminate()

            # Re-poll interval (also the hot-plug detection cadence).
            for _ in range(20):
                if not self._running:
                    return
                time.sleep(0.1)

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
